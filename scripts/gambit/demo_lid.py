"""
Lid open/close demo — fast replay with GIF recording.
Usage: python scripts/gambit/demo_lid.py [cycles]
"""
import json, time, sys, os, cv2, imageio
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.cobot.cached_robot import CachedRobot

CYCLES = int(sys.argv[1]) if len(sys.argv) > 1 else 2
CAMERA_IDS = [1, 2]
FLIP_CAMS = {1}
FPS = 8
GAMMA = 1.4
SPEED = 40       # faster than 25
STEP_DELAY = 0.2 # shorter pause between waypoints

RIGHT_IP = "192.168.0.5"
LEFT_IP = "192.168.0.6"
PORT = 9000
ACTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "taught_actions.json")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "visualizations")

with open(ACTIONS_PATH) as f:
    actions = json.load(f)

mc_r = CachedRobot(RIGHT_IP, PORT)
mc_l = CachedRobot(LEFT_IP, PORT)
mc_r.power_on()
mc_l.power_on()
time.sleep(1)

# Open cameras
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

lut = np.array([((i / 255.0) ** (1.0 / GAMMA)) * 255 for i in range(256)]).astype("uint8")


def capture():
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


def wait_done(mc, timeout=5):
    time.sleep(0.3)
    for _ in range(int(timeout / 0.15)):
        try:
            if not mc.is_moving():
                return
        except Exception:
            pass
        time.sleep(0.15)


def replay_close(all_frames):
    """Close lid: right preps, then left closes."""
    a = actions["close_lid"]
    if "phases" in a:
        p1 = a["phases"][0]
        p2 = a["phases"][1]
        wp_r = p1["right_waypoints"]
        wp_l = p2["left_waypoints"]

        # Phase 1: right prep
        for wr in wp_r:
            mc_r.send_angles(wr, SPEED)
            f = capture()
            if f is not None:
                all_frames.append(f)
            time.sleep(STEP_DELAY)
        wait_done(mc_r)

        # Phase 2: left close
        for wl in wp_l:
            mc_l.send_angles(wl, SPEED)
            f = capture()
            if f is not None:
                all_frames.append(f)
            time.sleep(STEP_DELAY)
        wait_done(mc_l)
    else:
        wp_r = a["right_waypoints"]
        wp_l = a["left_waypoints"]
        for wr, wl in zip(wp_r, wp_l):
            mc_r.send_angles(wr, SPEED)
            mc_l.send_angles(wl, SPEED)
            f = capture()
            if f is not None:
                all_frames.append(f)
            time.sleep(STEP_DELAY)
        wait_done(mc_r)
        wait_done(mc_l)


def replay_open(all_frames):
    """Open lid: both arms together."""
    a = actions["open_lid"]
    wp_r = a["right_waypoints"]
    wp_l = a["left_waypoints"]
    for wr, wl in zip(wp_r, wp_l):
        mc_r.send_angles(wr, SPEED)
        mc_l.send_angles(wl, SPEED)
        f = capture()
        if f is not None:
            all_frames.append(f)
        time.sleep(STEP_DELAY)
    wait_done(mc_r)
    wait_done(mc_l)


print(f"\nRunning {CYCLES} close/open cycles with {len(caps)} cameras...")
all_frames = []

f = capture()
if f is not None:
    all_frames.append(f)

try:
    for i in range(CYCLES):
        print(f"  Cycle {i+1}/{CYCLES}")
        mc_l.set_color(255, 0, 0)
        mc_r.set_color(0, 255, 255)
        replay_close(all_frames)

        mc_r.set_color(0, 255, 0)
        mc_l.set_color(0, 255, 0)
        replay_open(all_frames)
except KeyboardInterrupt:
    print("\n  Interrupted — saving...")

for cap in caps.values():
    cap.release()

mc_r.set_color(255, 255, 255)
mc_l.set_color(255, 255, 255)

gif_path = os.path.join(OUT_DIR, "demo_lid_open_close.gif")
print(f"\nSaving {len(all_frames)} frames...")
imageio.mimsave(gif_path, all_frames, duration=1.0 / FPS, loop=0)
print(f"Saved: {gif_path} ({os.path.getsize(gif_path) / 1024:.0f} KB)")
print("Done!")
