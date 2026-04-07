"""
Demo Showcase Loop — Typing + Touchpad gestures in a continuous loop.
Cycle: Type "Hello" + Enter x10 → Left click → Right click → Scroll up → Scroll down → Repeat.

Usage: python scripts/gambit/demo_showcase_loop.py
"""
import json, time, sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.cobot.cached_robot import CachedRobot

RIGHT_IP = "192.168.0.5"
LEFT_IP = "192.168.0.6"
PORT = 9000
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")

with open(os.path.join(DATA_DIR, "keyboard_taught.json")) as f:
    TAUGHT = json.load(f)["keys"]
with open(os.path.join(DATA_DIR, "touchpad_boundaries.json")) as f:
    TP = json.load(f)

# ── Robot connections ──
mc_r = CachedRobot(RIGHT_IP, PORT)
mc_l = CachedRobot(LEFT_IP, PORT)
mc_r.power_on(); mc_l.power_on()
time.sleep(0.5)

# ── Touchpad setup ──
LEFT_TL = TP["left"]["top_left"]["coords"]
LEFT_BL = TP["left"]["bottom_left"]["coords"]
RIGHT_TR = TP["right"]["top_right"]["coords"]
RIGHT_BR = TP["right"]["bottom_right"]["coords"]
LEFT_SZ = (LEFT_TL[2] + LEFT_BL[2]) / 2
RIGHT_SZ = (RIGHT_TR[2] + RIGHT_BR[2]) / 2

def avg_a(a, b):
    return math.degrees(math.atan2(
        math.sin(math.radians(a)) + math.sin(math.radians(b)),
        math.cos(math.radians(a)) + math.cos(math.radians(b))))

LRX = avg_a(LEFT_TL[3], LEFT_BL[3])
LRY = avg_a(LEFT_TL[4], LEFT_BL[4])
LRZ = avg_a(LEFT_TL[5], LEFT_BL[5])

L_SCROLL = [254.9, -51.8, LEFT_SZ + 9.5, 174.52, 1.9, -109.66]
R_SCROLL = [244.4, 27.3, RIGHT_SZ + 4.5, -177.32, 4.08, 16.25]
SD = 25
l_up = 1 if LEFT_TL[1] > LEFT_BL[1] else -1
r_up = 1 if RIGHT_TR[1] > RIGHT_BR[1] else -1

# Direction vectors for single-finger swipes (computed from corners)
_l_up_dy = LEFT_TL[1] - LEFT_BL[1]
_l_up_dx = LEFT_TL[0] - LEFT_BL[0]
_l_len = math.sqrt(_l_up_dy**2 + _l_up_dx**2)
L_UP_UX, L_UP_UY = _l_up_dx / _l_len, _l_up_dy / _l_len
L_LEFT_UX, L_LEFT_UY = L_UP_UY, -L_UP_UX

_r_up_dy = RIGHT_TR[1] - RIGHT_BR[1]
_r_up_dx = RIGHT_TR[0] - RIGHT_BR[0]
_r_len = math.sqrt(_r_up_dy**2 + _r_up_dx**2)
R_UP_UX, R_UP_UY = _r_up_dx / _r_len, _r_up_dy / _r_len
R_LEFT_UX, R_LEFT_UY = R_UP_UY, -R_UP_UX

# ── Helpers ──
HOVER_Z = 20
PRESS_Z = 3
TAP_Z = 8
CENTER_KEYS = set("6 7 y u g h b n t j".split())


def wait_still(mc, t=2.0):
    """Wait until arm stops, with hard timeout failsafe."""
    time.sleep(0.15)
    dl = time.time() + t
    while time.time() < dl:
        try:
            if not mc.is_moving():
                return
        except Exception:
            return  # connection issue — don't hang
        time.sleep(0.1)


def press_key(key):
    d = TAUGHT[key]
    c = d["coords"]
    arm = d.get("arm", "right")
    mc = mc_l if arm == "left" else mc_r
    x, y, z = c[0], c[1], c[2]
    mc.send_coords([x, y, z + HOVER_Z, 0, 180, 90], 40, 0)
    wait_still(mc, 1.5)
    mc.send_coords([x, y, z + TAP_Z, 0, 180, 90], 50, 0)
    wait_still(mc, 1.0)
    time.sleep(0.05)
    mc.send_coords([x, y, z - PRESS_Z, 0, 180, 90], 80, 0)
    time.sleep(0.08)
    mc.send_coords([x, y, z + HOVER_Z, 0, 180, 90], 80, 0)
    time.sleep(0.05)
    wait_still(mc, 1.0)


def type_text_fast(text):
    """Type with concurrent arms."""
    actions_list = []
    for ch in text:
        k = ch.lower() if ch != " " else "space"
        if k in TAUGHT:
            actions_list.append((k, TAUGHT[k]["coords"][:3], TAUGHT[k].get("arm", "right")))

    def next_for_arm(start, arm_name):
        for j in range(start, len(actions_list)):
            if actions_list[j][2] == arm_name:
                return j
        return -1

    for i, (key, coords, arm) in enumerate(actions_list):
        mc = mc_l if arm == "left" else mc_r
        other_mc = mc_r if arm == "left" else mc_l
        other_arm = "right" if arm == "left" else "left"
        x, y, z = coords

        if key in CENTER_KEYS:
            try:
                oc = other_mc.get_coords()
                if oc and oc != -1 and len(oc) >= 6:
                    nudge_y = 30 if other_arm == "left" else -30
                    other_mc.send_coords([oc[0], oc[1] + nudge_y, max(oc[2], z + HOVER_Z), 0, 180, 90], 40, 0)
            except Exception:
                pass
            time.sleep(0.3)

        mc.send_coords([x, y, z + HOVER_Z, 0, 180, 90], 40, 0)

        if key not in CENTER_KEYS:
            ni = next_for_arm(i + 1, other_arm)
            if ni >= 0:
                nk, nc, _ = actions_list[ni]
                if nk not in CENTER_KEYS:
                    other_mc.send_coords([nc[0], nc[1], nc[2] + HOVER_Z, 0, 180, 90], 40, 0)

        wait_still(mc, 1.5)
        # Two-stage tap: low hover → quick strike → immediate lift
        mc.send_coords([x, y, z + TAP_Z, 0, 180, 90], 50, 0)
        wait_still(mc, 1.0)
        time.sleep(0.05)  # brief settle before strike
        mc.send_coords([x, y, z - PRESS_Z, 0, 180, 90], 80, 0)
        time.sleep(0.08)  # ~80ms contact — short enough to avoid repeat
        mc.send_coords([x, y, z + HOVER_Z, 0, 180, 90], 80, 0)  # fast lift
        time.sleep(0.05)
        wait_still(mc, 1.0)


def tp_left_click():
    x = (LEFT_TL[0] + LEFT_BL[0]) / 2
    y = (LEFT_TL[1] + LEFT_BL[1]) / 2
    z = LEFT_SZ
    mc_l.send_coords([x, y, z + 25, LRX, LRY, LRZ], 30, 0)
    wait_still(mc_l)
    mc_l.send_coords([x, y, z - 6, LRX, LRY, LRZ], 80, 0)
    time.sleep(0.2)
    mc_l.send_coords([x, y, z + 25, LRX, LRY, LRZ], 50, 0)
    wait_still(mc_l)


def tp_right_click():
    bx, by, bz, brx, bry, brz = RIGHT_BR
    mc_r.send_coords([bx, by, bz + 25, brx, bry, brz], 30, 0)
    wait_still(mc_r)
    mc_r.send_coords([bx, by, bz - 6, brx, bry, brz], 80, 0)
    time.sleep(0.2)
    mc_r.send_coords([bx, by, bz + 25, brx, bry, brz], 50, 0)
    wait_still(mc_r)


def tp_scroll(direction):
    lx, ly, lz = L_SCROLL[0], L_SCROLL[1], L_SCROLL[2]
    lrx, lry, lrz = L_SCROLL[3], L_SCROLL[4], L_SCROLL[5]
    rx, ry, rz = R_SCROLL[0], R_SCROLL[1], R_SCROLL[2]
    rrx, rry, rrz = R_SCROLL[3], R_SCROLL[4], R_SCROLL[5]

    if direction == "up":
        lys, lye = ly, ly + l_up * SD
        rys, rye = ry, ry + r_up * SD
    else:
        lys, lye = ly + l_up * SD, ly
        rys, rye = ry + r_up * SD, ry

    mc_l.send_coords([lx, lys, lz + 25, lrx, lry, lrz], 30, 0)
    mc_r.send_coords([rx, rys, rz + 25, rrx, rry, rrz], 30, 0)
    wait_still(mc_l); wait_still(mc_r)
    mc_l.send_coords([lx, lys, lz, lrx, lry, lrz], 15, 0)
    mc_r.send_coords([rx, rys, rz, rrx, rry, rrz], 15, 0)
    wait_still(mc_l); wait_still(mc_r)
    time.sleep(0.3)
    mc_l.send_coords([lx, lye, lz, lrx, lry, lrz], 8, 0)
    mc_r.send_coords([rx, rye, rz, rrx, rry, rrz], 8, 0)
    wait_still(mc_l, 4); wait_still(mc_r, 4)
    mc_l.send_coords([lx, lye, lz + 25, lrx, lry, lrz], 40, 0)
    mc_r.send_coords([rx, rye, rz + 25, rrx, rry, rrz], 40, 0)
    wait_still(mc_l); wait_still(mc_r)


def home():
    mc_r.send_angles([0, 0, 0, 0, 0, 0], 30)
    mc_l.send_angles([0, 0, 0, 0, 0, 0], 30)
    time.sleep(2)


def single_swipe(mc, cx, cy, cz, rx, ry, rz, dx, dy):
    """Single-finger swipe: touch and slide in (dx, dy) direction."""
    hover = cz + 25
    sx, sy = cx - dx / 2, cy - dy / 2
    ex, ey = cx + dx / 2, cy + dy / 2
    mc.send_coords([sx, sy, hover, rx, ry, rz], 30, 0)
    wait_still(mc)
    mc.send_coords([sx, sy, cz, rx, ry, rz], 15, 0)
    wait_still(mc)
    time.sleep(0.3)
    mc.send_coords([ex, ey, cz, rx, ry, rz], 8, 0)
    wait_still(mc, 4)
    mc.send_coords([ex, ey, hover, rx, ry, rz], 40, 0)
    wait_still(mc)


# ════════════════════════════════════════════
# MAIN LOOP
# ════════════════════════════════════════════
print("╔══════════════════════════════════════╗")
print("║  DEMO SHOWCASE — Continuous Loop     ║")
print("║  Ctrl+C to stop                      ║")
print("╚══════════════════════════════════════╝\n")

cycle = 0
try:
    while True:
        cycle += 1
        print(f"\n{'='*50}")
        print(f"  CYCLE {cycle}")
        print(f"{'='*50}")

        # ── TYPING PHASE ──
        WORDS = ["hello", "asha", "paven", "ranjit", "hi"]
        print("\n  ── TYPING: Hello, Asha, Paven, Ranjit, Hi ──")
        mc_l.set_color(0, 255, 0)
        mc_r.set_color(0, 255, 0)
        for rep, word in enumerate(WORDS):
            print(f"    {rep+1}/{len(WORDS)}: ", end="", flush=True)
            type_text_fast(word)
            press_key("enter")
            print(f"{word} \u21b5")
        home()
        time.sleep(1)

        # ── TOUCHPAD PHASE ──
        print("\n  ── TOUCHPAD GESTURES ──")

        print("    Left click...", end="", flush=True)
        mc_l.set_color(0, 255, 0)
        tp_left_click()
        mc_l.set_color(255, 255, 255)
        print(" ok")
        time.sleep(0.5)

        print("    Right click...", end="", flush=True)
        mc_r.set_color(255, 0, 0)
        tp_right_click()
        mc_r.set_color(255, 255, 255)
        print(" ok")
        time.sleep(0.5)

        print("    Scroll down...", end="", flush=True)
        mc_l.set_color(0, 0, 255); mc_r.set_color(0, 0, 255)
        tp_scroll("down")
        print(" ok")
        time.sleep(0.5)

        print("    Scroll up...", end="", flush=True)
        tp_scroll("up")
        mc_l.set_color(255, 255, 255); mc_r.set_color(255, 255, 255)
        print(" ok")
        time.sleep(0.5)

        # Single-finger swipes: park idle arm to avoid collision
        print("    Left finger swipe left...", end="", flush=True)
        mc_r.send_angles([0, 0, 0, 0, 0, 0], 30)
        time.sleep(1.5)
        mc_l.set_color(0, 255, 255)
        lx, ly, lz = L_SCROLL[0], L_SCROLL[1], L_SCROLL[2]
        lrx, lry, lrz = L_SCROLL[3], L_SCROLL[4], L_SCROLL[5]
        single_swipe(mc_l, lx, ly, lz, lrx, lry, lrz, L_LEFT_UX * SD, L_LEFT_UY * SD)
        mc_l.set_color(255, 255, 255)
        print(" ok")
        time.sleep(0.5)

        print("    Right finger swipe down...", end="", flush=True)
        mc_l.send_angles([0, 0, 0, 0, 0, 0], 30)
        time.sleep(1.5)
        mc_r.set_color(255, 165, 0)
        rx, ry, rz = R_SCROLL[0], R_SCROLL[1], R_SCROLL[2]
        rrx, rry, rrz = R_SCROLL[3], R_SCROLL[4], R_SCROLL[5]
        single_swipe(mc_r, rx, ry, rz, rrx, rry, rrz, -R_UP_UX * SD, -R_UP_UY * SD)
        mc_r.set_color(255, 255, 255)
        print(" ok")
        time.sleep(0.5)

        home()
        print(f"\n  Cycle {cycle} complete!")
        time.sleep(1)

except KeyboardInterrupt:
    print(f"\n\n  Stopped after {cycle} cycles.")
    home()
    mc_r.set_color(255, 255, 255)
    mc_l.set_color(255, 255, 255)
    print("  Arms homed. Done!")
