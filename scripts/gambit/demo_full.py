"""
Full Surface Laptop Demo — Lid, Login, Type, Touchpad.
Each phase saves a separate GIF.

Usage: python scripts/gambit/demo_full.py
"""
import json, time, sys, os, cv2, imageio, math
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.cobot.cached_robot import CachedRobot

RIGHT_IP = "192.168.0.5"
LEFT_IP = "192.168.0.6"
PORT = 9000
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "visualizations")
ACTIONS_PATH = os.path.join(DATA_DIR, "taught_actions.json")

CAMERA_IDS = [1, 2]
FLIP_CAMS = {1}
FPS = 8
GAMMA = 1.4
LID_SPEED = 40
LID_DELAY = 0.2

# Load data
with open(ACTIONS_PATH) as f:
    lid_actions = json.load(f)
with open(os.path.join(DATA_DIR, "keyboard_taught.json")) as f:
    TAUGHT = json.load(f)["keys"]
with open(os.path.join(DATA_DIR, "touchpad_boundaries.json")) as f:
    TP = json.load(f)

# ── Robot connections ──
mc_r = CachedRobot(RIGHT_IP, PORT)
mc_l = CachedRobot(LEFT_IP, PORT)
mc_r.power_on()
mc_l.power_on()
time.sleep(1)

# ── Camera setup ──
lut = np.array([((i / 255.0) ** (1.0 / GAMMA)) * 255 for i in range(256)]).astype("uint8")
caps = {}
for cid in CAMERA_IDS:
    cap = cv2.VideoCapture(cid, cv2.CAP_DSHOW)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        for _ in range(10):
            cap.read()
        caps[cid] = cap
        print(f"Camera {cid}: OK")


def snap():
    frames = []
    for cid, cap in caps.items():
        cap.read()
        ret, frame = cap.read()
        if ret:
            if cid in FLIP_CAMS:
                frame = cv2.flip(frame, -1)
            frame = cv2.resize(frame, (320, 240))
            frame = cv2.LUT(frame, lut)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame)
    return np.hstack(frames) if frames else None


def save_gif(frames, name):
    path = os.path.join(OUT_DIR, name)
    imageio.mimsave(path, frames, duration=1.0 / FPS, loop=0)
    print(f"  Saved {name} ({len(frames)} frames, {os.path.getsize(path)//1024} KB)")


def wait_done(mc, timeout=5):
    time.sleep(0.3)
    for _ in range(int(timeout / 0.15)):
        try:
            if not mc.is_moving():
                return
        except Exception:
            pass
        time.sleep(0.15)


def wait_still(mc, timeout=2.0):
    time.sleep(0.2)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if not mc.is_moving():
                return
        except Exception:
            pass
        time.sleep(0.1)


# ────────────────────────────────────────────
# Keyboard helpers
# ────────────────────────────────────────────
HOVER_Z = 20
PRESS_Z = 3
TAP_Z = 8
CENTER_KEYS = set("6 7 y u g h b n t j".split())


def get_pos(ch):
    k = ch.lower()
    if k == " ":
        k = "space"
    if k not in TAUGHT:
        return None, None
    d = TAUGHT[k]
    return list(d["coords"][:3]), d.get("arm", "right")


def press_key(ch, frames):
    """Press a single key, capturing frames."""
    coords, arm = get_pos(ch)
    if coords is None:
        print(f"  {ch} - no position")
        return
    mc = mc_l if arm == "left" else mc_r
    x, y, z = coords
    hover_z = z + HOVER_Z
    press_z = z - PRESS_Z
    tap_z = z + TAP_Z

    mc.send_coords([x, y, hover_z, 0, 180, 90], 40, 0)
    wait_still(mc, 1.5)
    f = snap()
    if f is not None:
        frames.append(f)

    mc.send_coords([x, y, tap_z, 0, 180, 90], 50, 0)
    wait_still(mc, 1.0)

    mc.send_coords([x, y, press_z, 0, 180, 90], 80, 0)
    time.sleep(0.1)
    mc.send_coords([x, y, hover_z, 0, 180, 90], 50, 0)
    time.sleep(0.1)
    wait_still(mc, 1.0)
    f = snap()
    if f is not None:
        frames.append(f)
    print(f"  {ch.upper()}", end="", flush=True)


def type_text_with_frames(text, frames):
    """Type text with concurrent arms, capturing frames."""
    actions_list = []
    for ch in text:
        coords, arm = get_pos(ch)
        if coords:
            actions_list.append((ch, coords, arm))

    def next_for_arm(start, arm_name):
        for j in range(start, len(actions_list)):
            if actions_list[j][2] == arm_name:
                return j
        return -1

    for i, (ch, coords, arm) in enumerate(actions_list):
        mc = mc_l if arm == "left" else mc_r
        other_mc = mc_r if arm == "left" else mc_l
        other_arm = "right" if arm == "left" else "left"
        x, y, z = coords
        hover_z = z + HOVER_Z
        press_z = z - PRESS_Z
        tap_z = z + TAP_Z
        key_name = ch.lower() if ch != " " else "space"

        if key_name in CENTER_KEYS:
            try:
                oc = other_mc.get_coords()
                if oc and oc != -1 and len(oc) >= 6:
                    nudge_y = 30 if other_arm == "left" else -30
                    safe_z = max(oc[2], z + HOVER_Z)
                    other_mc.send_coords([oc[0], oc[1] + nudge_y, safe_z, 0, 180, 90], 40, 0)
            except Exception:
                pass
            time.sleep(0.3)

        mc.send_coords([x, y, hover_z, 0, 180, 90], 40, 0)

        if key_name not in CENTER_KEYS:
            ni = next_for_arm(i + 1, other_arm)
            if ni >= 0:
                nch, nc, _ = actions_list[ni]
                nk = nch.lower() if nch != " " else "space"
                if nk not in CENTER_KEYS:
                    other_mc.send_coords([nc[0], nc[1], nc[2] + HOVER_Z, 0, 180, 90], 40, 0)

        wait_still(mc, 1.5)
        f = snap()
        if f is not None:
            frames.append(f)

        mc.send_coords([x, y, tap_z, 0, 180, 90], 50, 0)
        wait_still(mc, 1.0)

        mc.send_coords([x, y, press_z, 0, 180, 90], 80, 0)
        time.sleep(0.1)
        mc.send_coords([x, y, hover_z, 0, 180, 90], 50, 0)
        time.sleep(0.1)
        wait_still(mc, 1.0)
        f = snap()
        if f is not None:
            frames.append(f)
        print(f" {ch.upper()}" if ch != " " else " SPC", end="", flush=True)
    print()


# ────────────────────────────────────────────
# Touchpad helpers
# ────────────────────────────────────────────
LEFT_TL = TP["left"]["top_left"]["coords"]
LEFT_BL = TP["left"]["bottom_left"]["coords"]
RIGHT_TR = TP["right"]["top_right"]["coords"]
RIGHT_BR = TP["right"]["bottom_right"]["coords"]
LEFT_SURFACE_Z = (LEFT_TL[2] + LEFT_BL[2]) / 2
RIGHT_SURFACE_Z = (RIGHT_TR[2] + RIGHT_BR[2]) / 2


def avg_angle(a, b):
    r = math.atan2(math.sin(math.radians(a)) + math.sin(math.radians(b)),
                   math.cos(math.radians(a)) + math.cos(math.radians(b)))
    return math.degrees(r)


LEFT_RX = avg_angle(LEFT_TL[3], LEFT_BL[3])
LEFT_RY = avg_angle(LEFT_TL[4], LEFT_BL[4])
LEFT_RZ = avg_angle(LEFT_TL[5], LEFT_BL[5])
RIGHT_RX = avg_angle(RIGHT_TR[3], RIGHT_BR[3])
RIGHT_RY = avg_angle(RIGHT_TR[4], RIGHT_BR[4])
RIGHT_RZ = avg_angle(RIGHT_TR[5], RIGHT_BR[5])

TP_HOVER = 25
TP_CLICK_MM = 6
TP_SCROLL_DIST = 25
L_SCROLL = [254.9, -51.8, LEFT_SURFACE_Z + 6, 174.52, 1.9, -109.66]
R_SCROLL = [244.4, 27.3, 46.9, -177.32, 4.08, 16.25]


def lerp(a, b, t):
    return [a[i] + (b[i] - a[i]) * t for i in range(len(a))]


def tp_left_click(frames):
    target = lerp(LEFT_TL, LEFT_BL, 0.5)
    x, y, z = target[0], target[1], LEFT_SURFACE_Z
    mc_l.send_coords([x, y, z + TP_HOVER, LEFT_RX, LEFT_RY, LEFT_RZ], 30, 0)
    wait_still(mc_l)
    f = snap()
    if f is not None:
        frames.append(f)
    mc_l.send_coords([x, y, z - TP_CLICK_MM, LEFT_RX, LEFT_RY, LEFT_RZ], 80, 0)
    time.sleep(0.2)
    mc_l.send_coords([x, y, z + TP_HOVER, LEFT_RX, LEFT_RY, LEFT_RZ], 50, 0)
    wait_still(mc_l)
    f = snap()
    if f is not None:
        frames.append(f)


def tp_right_click(frames):
    x, y, z = RIGHT_BR[0], RIGHT_BR[1], RIGHT_BR[2]
    rx, ry, rz = RIGHT_BR[3], RIGHT_BR[4], RIGHT_BR[5]
    mc_r.send_coords([x, y, z + TP_HOVER, rx, ry, rz], 30, 0)
    wait_still(mc_r)
    f = snap()
    if f is not None:
        frames.append(f)
    mc_r.send_coords([x, y, z - TP_CLICK_MM, rx, ry, rz], 80, 0)
    time.sleep(0.2)
    mc_r.send_coords([x, y, z + TP_HOVER, rx, ry, rz], 50, 0)
    wait_still(mc_r)
    f = snap()
    if f is not None:
        frames.append(f)


def tp_scroll(direction, frames):
    lx, ly, lz = L_SCROLL[0], L_SCROLL[1], L_SCROLL[2]
    lrx, lry, lrz = L_SCROLL[3], L_SCROLL[4], L_SCROLL[5]
    rx, ry, rz = R_SCROLL[0], R_SCROLL[1], R_SCROLL[2]
    rrx, rry, rrz = R_SCROLL[3], R_SCROLL[4], R_SCROLL[5]

    l_up = 1 if LEFT_TL[1] > LEFT_BL[1] else -1
    r_up = 1 if RIGHT_TR[1] > RIGHT_BR[1] else -1

    if direction == "up":
        ly_s, ly_e = ly, ly + l_up * TP_SCROLL_DIST
        ry_s, ry_e = ry, ry + r_up * TP_SCROLL_DIST
    else:
        ly_s, ly_e = ly + l_up * TP_SCROLL_DIST, ly
        ry_s, ry_e = ry + r_up * TP_SCROLL_DIST, ry

    mc_l.send_coords([lx, ly_s, lz + TP_HOVER, lrx, lry, lrz], 30, 0)
    mc_r.send_coords([rx, ry_s, rz + TP_HOVER, rrx, rry, rrz], 30, 0)
    wait_still(mc_l); wait_still(mc_r)
    f = snap()
    if f is not None:
        frames.append(f)

    mc_l.send_coords([lx, ly_s, lz, lrx, lry, lrz], 15, 0)
    mc_r.send_coords([rx, ry_s, rz, rrx, rry, rrz], 15, 0)
    wait_still(mc_l); wait_still(mc_r)
    time.sleep(0.3)

    mc_l.send_coords([lx, ly_e, lz, lrx, lry, lrz], 8, 0)
    mc_r.send_coords([rx, ry_e, rz, rrx, rry, rrz], 8, 0)
    wait_still(mc_l, 4); wait_still(mc_r, 4)
    f = snap()
    if f is not None:
        frames.append(f)

    mc_l.send_coords([lx, ly_e, lz + TP_HOVER, lrx, lry, lrz], 40, 0)
    mc_r.send_coords([rx, ry_e, rz + TP_HOVER, rrx, rry, rrz], 40, 0)
    wait_still(mc_l); wait_still(mc_r)
    f = snap()
    if f is not None:
        frames.append(f)


# ────────────────────────────────────────────
# Lid helpers
# ────────────────────────────────────────────
def lid_close(frames):
    a = lid_actions["close_lid"]
    if "phases" in a:
        for wr in a["phases"][0]["right_waypoints"]:
            mc_r.send_angles(wr, LID_SPEED)
            f = snap()
            if f is not None:
                frames.append(f)
            time.sleep(LID_DELAY)
        wait_done(mc_r)
        for wl in a["phases"][1]["left_waypoints"]:
            mc_l.send_angles(wl, LID_SPEED)
            f = snap()
            if f is not None:
                frames.append(f)
            time.sleep(LID_DELAY)
        wait_done(mc_l)
    else:
        for wr, wl in zip(a["right_waypoints"], a["left_waypoints"]):
            mc_r.send_angles(wr, LID_SPEED)
            mc_l.send_angles(wl, LID_SPEED)
            f = snap()
            if f is not None:
                frames.append(f)
            time.sleep(LID_DELAY)
        wait_done(mc_r); wait_done(mc_l)


def lid_open(frames):
    a = lid_actions["open_lid"]
    for wr, wl in zip(a["right_waypoints"], a["left_waypoints"]):
        mc_r.send_angles(wr, LID_SPEED)
        mc_l.send_angles(wl, LID_SPEED)
        f = snap()
        if f is not None:
            frames.append(f)
        time.sleep(LID_DELAY)
    wait_done(mc_r); wait_done(mc_l)


def home():
    mc_r.send_angles([0, 0, 0, 0, 0, 0], 30)
    mc_l.send_angles([0, 0, 0, 0, 0, 0], 30)
    time.sleep(2)
    wait_done(mc_r); wait_done(mc_l)


# ════════════════════════════════════════════
# DEMO SEQUENCE
# ════════════════════════════════════════════
print("\n╔══════════════════════════════════════╗")
print("║  FULL SURFACE LAPTOP DEMO            ║")
print("╚══════════════════════════════════════╝\n")

try:
    # ── PHASE 1: LID ──
    print("── PHASE 1: LID CLOSE + OPEN ──")
    input("  Lid should be OPEN. Press ENTER to start...")
    frames = []
    f = snap()
    if f is not None:
        frames.append(f)
    mc_l.set_color(255, 0, 0)
    mc_r.set_color(0, 255, 255)
    lid_close(frames)
    time.sleep(1)
    mc_r.set_color(0, 255, 0)
    mc_l.set_color(0, 255, 0)
    lid_open(frames)
    home()
    save_gif(frames, "Demo_lid.gif")

    # ── PHASE 2: LOGIN ──
    print("\n── PHASE 2: LOGIN ──")
    input("  Login screen should be showing. Press ENTER to start...")
    frames = []
    f = snap()
    if f is not None:
        frames.append(f)
    print("  Pressing ENTER to dismiss lock screen...")
    press_key("enter", frames)
    time.sleep(2)
    # Capture a few frames while PIN screen appears
    for _ in range(4):
        f = snap()
        if f is not None:
            frames.append(f)
        time.sleep(0.5)
    print("  Typing PIN: 199715")
    for digit in "199715":
        press_key(digit, frames)
        time.sleep(0.3)
    print()
    # Press Enter to submit
    print("  Pressing ENTER to submit...")
    press_key("enter", frames)
    time.sleep(3)
    # Capture login result
    for _ in range(6):
        f = snap()
        if f is not None:
            frames.append(f)
        time.sleep(0.5)
    home()
    save_gif(frames, "Demo_login.gif")

    # ── PHASE 3: TYPE ──
    print("\n── PHASE 3: TYPE 'Hello World' ──")
    input("  Open a text editor, then press ENTER to start...")
    frames = []
    f = snap()
    if f is not None:
        frames.append(f)
    print("  Typing: Hello World")
    # Type H (shift not needed if we just press the key — it types lowercase)
    # We'll type "hello world" in lowercase since we don't have shift combos
    type_text_with_frames("hello world", frames)
    time.sleep(1)
    for _ in range(4):
        f = snap()
        if f is not None:
            frames.append(f)
        time.sleep(0.5)
    home()
    save_gif(frames, "Demo_type.gif")

    # ── PHASE 4: TOUCHPAD ──
    print("\n── PHASE 4: TOUCHPAD GESTURES ──")
    input("  Close text editor if needed. Press ENTER to start...")
    frames = []
    f = snap()
    if f is not None:
        frames.append(f)

    print("  Left click...")
    mc_l.set_color(0, 255, 0)
    tp_left_click(frames)
    mc_l.set_color(255, 255, 255)
    time.sleep(1)

    print("  Right click...")
    mc_r.set_color(255, 0, 0)
    tp_right_click(frames)
    mc_r.set_color(255, 255, 255)
    time.sleep(1)

    print("  Scroll up...")
    mc_l.set_color(0, 0, 255)
    mc_r.set_color(0, 0, 255)
    tp_scroll("up", frames)
    time.sleep(1)

    print("  Scroll down...")
    tp_scroll("down", frames)
    mc_l.set_color(255, 255, 255)
    mc_r.set_color(255, 255, 255)
    time.sleep(1)

    for _ in range(3):
        f = snap()
        if f is not None:
            frames.append(f)
        time.sleep(0.3)
    home()
    save_gif(frames, "Demo_touchpad.gif")

    print("\n✓ ALL DEMOS COMPLETE!")

except KeyboardInterrupt:
    print("\n  Interrupted!")
finally:
    for cap in caps.values():
        cap.release()
    mc_r.set_color(255, 255, 255)
    mc_l.set_color(255, 255, 255)
