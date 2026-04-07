"""
Teach Touchpad Boundaries — Each arm teaches its reachable half.
================================================================
Left arm  → left half  (top-left, bottom-left corners)
Right arm → right half (top-right, bottom-right corners)

Together the 4 corners define the full touchpad rectangle.

Touchpad zone map (XML: offset X=80 Y=120, size 111×90 mm):
  ┌─────────────┬─────────────┐
  │  LEFT ARM   │  RIGHT ARM  │
  │  TOP-LEFT   │  TOP-RIGHT  │
  │  (left clk) │  (left clk) │
  ├─────────────┼─────────────┤
  │  LEFT ARM   │  RIGHT ARM  │
  │  BOT-LEFT   │  BOT-RIGHT  │
  │  (left clk) │ (RIGHT clk) │
  └─────────────┴─────────────┘

Run: python scripts/gambit/teach_touchpad_bounds.py
"""
import json
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.cobot.cached_robot import CachedRobot

RIGHT_IP = "192.168.0.5"
LEFT_IP = "192.168.0.6"
PORT = 9000

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
OUT_PATH = os.path.join(DATA_DIR, "touchpad_boundaries.json")

# Each arm only teaches the corners it can reach
LEFT_CORNERS = ["top_left", "bottom_left"]
RIGHT_CORNERS = ["top_right", "bottom_right"]

CORNER_LABELS = {
    "top_left":     "TOP-LEFT     (far-left, away from you)",
    "top_right":    "TOP-RIGHT    (far-right, away from you)",
    "bottom_left":  "BOTTOM-LEFT  (near-left, closest to you)",
    "bottom_right": "BOTTOM-RIGHT (near-right, closest to you)",
}


def read_stable_coords(robot, samples=5, delay=0.3):
    """Read coords multiple times and average for stability."""
    coords_list = []
    for _ in range(samples):
        time.sleep(delay)
        c = robot.get_coords()
        if c and c != -1 and len(c) == 6:
            coords_list.append(c)
    if not coords_list:
        return None
    avg = [sum(x) / len(x) for x in zip(*coords_list)]
    return [round(v, 2) for v in avg]


def teach_arm(name, ip, corners_to_teach):
    """Teach touchpad corners for one arm. Returns dict of corner coords."""
    print(f"\n{'='*55}")
    print(f"  Teaching {name.upper()} ARM  ({ip})")
    print(f"  Corners: {', '.join(corners_to_teach)}")
    print(f"{'='*55}")

    robot = CachedRobot(ip, PORT)
    robot.power_on()
    time.sleep(0.5)

    corners = {}
    robot.set_color(0, 255, 255)
    robot.release_all_servos()
    time.sleep(0.5)

    print(f"\n  Servos released. Drag the {name} arm tip to each corner.")
    print("  Gently press the tip on the touchpad surface at each corner.\n")

    for corner in corners_to_teach:
        label = CORNER_LABELS[corner]
        input(f"  → Move to {label}, then press ENTER...")

        print("    Reading position (hold still ~2s)...", end="", flush=True)
        coords = read_stable_coords(robot)
        if coords:
            x, y, z = coords[0], coords[1], coords[2]
            print(f" ({x:.1f}, {y:.1f}, {z:.1f})")
            corners[corner] = {"x": x, "y": y, "z": z, "coords": coords}
        else:
            print(" FAILED — couldn't read coordinates!")
            corners[corner] = None

    # Lock servos and return to safe pos
    robot.focus_all_servos()
    time.sleep(0.5)
    robot.set_color(255, 255, 255)

    # Print summary for this arm
    print(f"\n  {name.upper()} arm corners:")
    for corner in corners_to_teach:
        c = corners[corner]
        if c:
            print(f"    {corner:15s}  X={c['x']:7.1f}  Y={c['y']:7.1f}  Z={c['z']:7.1f}")
        else:
            print(f"    {corner:15s}  (not recorded)")

    return corners


def main():
    print("╔═══════════════════════════════════════════════╗")
    print("║  TEACH TOUCHPAD BOUNDARIES — Left/Right Half  ║")
    print("╚═══════════════════════════════════════════════╝")
    print()
    print("  Left arm  → top-left  + bottom-left  corners")
    print("  Right arm → top-right + bottom-right corners")
    print("  Together they define the full touchpad rectangle.")

    # Load existing data if any
    data = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            data = json.load(f)

    # Ask which arm(s) to teach
    print("\n  Which arm to teach?")
    print("    [L] Left arm  (top-left, bottom-left)")
    print("    [R] Right arm (top-right, bottom-right)")
    print("    [B] Both arms")
    choice = input("  → Choice (L/R/B): ").strip().upper()

    if choice in ("L", "B"):
        data["left"] = teach_arm("left", LEFT_IP, LEFT_CORNERS)
    if choice in ("R", "B"):
        data["right"] = teach_arm("right", RIGHT_IP, RIGHT_CORNERS)

    # Merge all 4 corners from both arms for combined bounds
    all_corners = {}
    for arm_name in ("left", "right"):
        arm = data.get(arm_name)
        if arm:
            for k, v in arm.items():
                if k in CORNER_LABELS:
                    all_corners[k] = v

    tl = all_corners.get("top_left")
    tr = all_corners.get("top_right")
    bl = all_corners.get("bottom_left")
    br = all_corners.get("bottom_right")

    if all(c for c in [tl, tr, bl, br]):
        cx = (tl["x"] + tr["x"] + bl["x"] + br["x"]) / 4
        cy = (tl["y"] + tr["y"] + bl["y"] + br["y"]) / 4
        cz = (tl["z"] + tr["z"] + bl["z"] + br["z"]) / 4

        data["combined"] = {
            "top_left": tl, "top_right": tr,
            "bottom_left": bl, "bottom_right": br,
            "center": {"x": round(cx, 2), "y": round(cy, 2), "z": round(cz, 2)},
            "x_range": [round(min(tl["x"], bl["x"]), 2), round(max(tr["x"], br["x"]), 2)],
            "y_range": [round(min(tl["y"], tr["y"]), 2), round(max(bl["y"], br["y"]), 2)],
        }

        print(f"\n  COMBINED touchpad bounds (both arms):")
        print(f"    Center: ({cx:.1f}, {cy:.1f}, {cz:.1f})")
        print(f"    X range: {data['combined']['x_range'][0]:.1f} → {data['combined']['x_range'][1]:.1f}")
        print(f"    Y range: {data['combined']['y_range'][0]:.1f} → {data['combined']['y_range'][1]:.1f}")
    else:
        have = [k for k in ["top_left", "top_right", "bottom_left", "bottom_right"] if k in all_corners]
        need = [k for k in ["top_left", "top_right", "bottom_left", "bottom_right"] if k not in all_corners]
        print(f"\n  Have corners: {', '.join(have)}")
        print(f"  Still need:   {', '.join(need)}")
        print("  (Teach the other arm to complete the rectangle)")

    # Save
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  ✓ Saved to {OUT_PATH}")
    print("  Done!")


if __name__ == "__main__":
    main()
