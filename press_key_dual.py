"""
Dual-arm key presser: uses the correct arm for each key based on reachability.
Left arm handles left-side keys, right arm handles right-side keys.
"""
from pymycobot import MyCobot280Socket
import numpy as np
import time
import json
import sys
import os

# Load dual-arm layout
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
with open(os.path.join(DATA_DIR, "keyboard_dual_arm.json"), "r") as f:
    layout = json.load(f)

MERGED_KEYS = layout.get("merged_keys", {})
ARMS_DATA = layout.get("arms", {})
print(f"Loaded {len(MERGED_KEYS)} keys across {len(ARMS_DATA)} arms")

# Speed profiles
PROFILES = {
    "slow":   {"slide": 12, "press": 6, "approach": 8,
               "slide_wait": 1.5, "press_wait": 1.2, "release_wait": 1.0, "start_wait": 3},
    "medium": {"slide": 20, "press": 12, "approach": 15,
               "slide_wait": 0.8, "press_wait": 0.6, "release_wait": 0.5, "start_wait": 2},
    "fast":   {"slide": 40, "press": 30, "approach": 30,
               "slide_wait": 0.3, "press_wait": 0.2, "release_wait": 0.2, "start_wait": 1.0},
}

HOVER_Z_OFFSET = 15  # mm above keyboard surface
PRESS_Z_OFFSET = 3   # mm below surface to register
SAFE_Z = 200


def wait_done(mc, timeout=2.0, min_wait=0.15):
    time.sleep(min_wait)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if mc.is_moving() == 0:
                return
        except:
            pass
        time.sleep(0.05)


def get_key_info(key_name):
    """Get key position and which arm to use."""
    key = key_name.lower()
    if key in MERGED_KEYS:
        data = MERGED_KEYS[key]
        # Support both "coords" format and "robot" format
        if "coords" in data:
            return data["coords"][:3], data["arm"]
        elif "robot" in data:
            return data["robot"][:3], data["arm"]
    return None, None


def type_text_dual(mc_right, mc_left, text, sp):
    """Type text using both arms — each key routed to the correct arm."""
    print(f"\n{'='*55}")
    print(f"  TYPING: '{text}' [dual-arm, {sp_name}]")
    print(f"{'='*55}")

    # Plan: group consecutive keys by arm for smooth motion
    keys = []
    for ch in text:
        k = 'space' if ch == ' ' else ch.lower()
        pos, arm = get_key_info(k)
        if pos is None:
            print(f"  Skipping '{k}' (unknown)")
            continue
        x, y, z = pos
        if not (-281 <= x <= 281):
            print(f"  Skipping '{k}' (out of reach)")
            continue
        keys.append((k, pos, arm))

    if not keys:
        print("  No valid keys!")
        return

    # Get arm connections
    arm_mc = {"right": mc_right, "left": mc_left}

    # Move both arms to safe height first
    for mc in [mc_right, mc_left]:
        if mc:
            mc.send_angles([0, 0, 0, 0, 0, 0], 15)
    time.sleep(3)

    current_arm = None
    hover_z = None

    for i, (key, (x, y, z), arm) in enumerate(keys):
        mc = arm_mc.get(arm)
        if mc is None:
            print(f"  Skipping '{key}' (arm '{arm}' not connected)")
            continue

        press_z = z - PRESS_Z_OFFSET
        hover_z = z + HOVER_Z_OFFSET

        # If switching arms, retract the previous arm first
        if current_arm and current_arm != arm:
            prev_mc = arm_mc[current_arm]
            prev_mc.send_coords([x, y, SAFE_Z, 0, 180, 90], sp["approach"], 0)
            time.sleep(1)

        if current_arm != arm:
            # New arm: approach from safe height
            mc.set_color(255, 100, 0)
            mc.send_coords([x, y, hover_z, 0, 180, 90], sp["approach"], 0)
            wait_done(mc, timeout=sp["start_wait"] + 1.0, min_wait=0.3)
            current_arm = arm
        else:
            # Same arm: slide at hover height
            mc.send_coords([x, y, hover_z, 0, 180, 90], sp["slide"], 0)
            wait_done(mc, timeout=sp["slide_wait"] + 1.0, min_wait=0.2)

        # Press
        mc.send_coords([x, y, press_z, 0, 180, 90], sp["press"], 0)
        wait_done(mc, timeout=sp["press_wait"] + 1.0, min_wait=0.4)
        time.sleep(0.1)

        # Release
        mc.send_coords([x, y, hover_z, 0, 180, 90], sp["press"], 0)
        wait_done(mc, timeout=sp["release_wait"] + 1.0, min_wait=0.3)

        print(f"  [{arm[0].upper()}] '{key}' ({i+1}/{len(keys)})")

    # Return both arms home
    for mc in [mc_right, mc_left]:
        if mc:
            mc.send_coords([200, 0, SAFE_Z, 0, 180, 90], sp["approach"], 0)
    time.sleep(2)
    for mc in [mc_right, mc_left]:
        if mc:
            mc.send_angles([0, 0, 0, 0, 0, 0], 15)
    time.sleep(3)
    for mc in [mc_right, mc_left]:
        if mc:
            mc.set_color(255, 255, 255)

    print(f"\n  Done typing '{text}'!")


if __name__ == "__main__":
    sp_name = "fast"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a in ("--fast", "--medium", "--slow"):
            sp_name = a[2:]
    sp = PROFILES[sp_name]

    # Connect both arms
    print("Connecting arms...")
    mc_right = MyCobot280Socket("10.105.230.93", 9000)
    time.sleep(1)
    mc_left = MyCobot280Socket("10.105.230.94", 9000)
    time.sleep(1)

    if args:
        text = " ".join(args)
        type_text_dual(mc_right, mc_left, text, sp)
    else:
        print(f"\nDual-arm interactive mode [{sp_name}]. Type text or 'quit'.\n")
        while True:
            cmd = input("Type: ").strip()
            if not cmd or cmd == "quit":
                break
            type_text_dual(mc_right, mc_left, cmd, sp)

    for mc in [mc_right, mc_left]:
        mc.send_angles([0, 0, 0, 0, 0, 0], 10)
    time.sleep(3)
    print("Done!")
