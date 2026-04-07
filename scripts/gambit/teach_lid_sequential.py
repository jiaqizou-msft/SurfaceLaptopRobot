"""
Teach Lid Open/Close — Sequential Arm Teaching
===============================================
Left arm = lid closer.  Right arm = lid opener.
Assumes lid starts OPEN.

Lid close sequence:
  1. Right arm preps (finger between lids to prevent full close)
  2. Left arm closes the lid (right arm stays still)

Lid open sequence:
  1. Right arm opens the lid
  2. Left arm stays parked

Each arm is taught one at a time:
  - Release that arm only
  - User drags it through the motion
  - Press Enter to start/stop recording
  - Lock servos, move to next arm

Run: python scripts/gambit/teach_lid_sequential.py
"""
import json
import time
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.cobot.cached_robot import CachedRobot

RIGHT_IP = "192.168.0.5"
LEFT_IP = "192.168.0.6"
PORT = 9000

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
ACTIONS_PATH = os.path.join(DATA_DIR, "taught_actions.json")

# Load existing actions
actions = {}
if os.path.exists(ACTIONS_PATH):
    with open(ACTIONS_PATH) as f:
        actions = json.load(f)


def record_arm(robot, name, color):
    """Release one arm, record drag trajectory, return downsampled waypoints."""
    robot.set_color(*color)
    robot.release_all_servos()
    time.sleep(0.5)

    print(f"\n  *** {name} ARM RELEASED ***")
    print(f"  Position the arm, then press ENTER to START recording.")
    input(f"  → ENTER to start recording {name} arm...")

    print(f"  *** RECORDING {name} — drag now! ***")
    robot.set_color(255, 0, 0)

    recording = True
    waypoints = []

    def loop():
        while recording:
            a = robot.get_angles()
            if a and a != -1 and isinstance(a, list) and len(a) == 6:
                waypoints.append([round(v, 2) for v in a])
            time.sleep(0.1)

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    input(f"  → ENTER to STOP recording {name} arm...")
    recording = False
    time.sleep(0.3)

    robot.focus_all_servos()
    time.sleep(0.5)
    robot.set_color(0, 255, 0)

    print(f"  Recorded {len(waypoints)} raw samples ({len(waypoints)/10:.1f}s)")

    if len(waypoints) < 3:
        print("  Too few waypoints!")
        return None

    # Downsample to ~20 waypoints
    step = max(1, len(waypoints) // 20)
    wp = waypoints[::step]
    if waypoints[-1] != wp[-1]:
        wp.append(waypoints[-1])

    print(f"  Downsampled to {len(wp)} waypoints")
    return wp


def get_parked_angles(robot):
    """Read current angles as the parked/stationary position."""
    angles = robot.get_angles()
    if angles and angles != -1:
        return [round(v, 2) for v in angles]
    return [0, 0, 0, 0, 0, 0]


def pad_static(static_angles, count):
    """Create a list of identical waypoints to match the active arm's count."""
    return [list(static_angles) for _ in range(count)]


def replay_action(mc_r, mc_l, action_data, label):
    """Replay a taught action sequentially."""
    wp_r = action_data["right_waypoints"]
    wp_l = action_data["left_waypoints"]
    method = action_data.get("method", "")

    print(f"\n  Replaying '{label}' ({len(wp_r)} waypoints)...")
    for i, (wr, wl) in enumerate(zip(wp_r, wp_l)):
        if "right_arm" in method:
            mc_r.send_angles(wr, 25)
        elif "left_arm" in method:
            mc_l.send_angles(wl, 25)
        else:
            mc_r.send_angles(wr, 25)
            mc_l.send_angles(wl, 25)
        time.sleep(0.4)

    # Wait for active arm to stop
    active = mc_r if "right_arm" in method else mc_l
    for _ in range(30):
        try:
            if not active.is_moving():
                break
        except Exception:
            break
        time.sleep(0.2)
    time.sleep(0.5)
    print("  Replay done!")


def main():
    print("╔════════════════════════════════════════════════╗")
    print("║  TEACH LID — Sequential Arm Recording          ║")
    print("║  Left=closer, Right=opener, one arm at a time  ║")
    print("╚════════════════════════════════════════════════╝")

    mc_r = CachedRobot(RIGHT_IP, PORT)
    mc_l = CachedRobot(LEFT_IP, PORT)
    mc_r.power_on()
    mc_l.power_on()
    time.sleep(1)

    print("\n  Which action to teach?")
    print("    1. Close lid  (right preps → left closes)")
    print("    2. Open lid   (right opens)")
    print("    3. Both       (close first, then open)")
    choice = input("  → Choice (1/2/3): ").strip()

    # ── TEACH CLOSE LID ──
    if choice in ("1", "3"):
        print("\n" + "=" * 55)
        print("  TEACHING: CLOSE LID")
        print("  Step 1: Right arm PREPS (finger between lids)")
        print("  Step 2: Left arm CLOSES the lid")
        print("=" * 55)

        # Step 1: Right arm prep
        print("\n  ── Step 1: RIGHT arm prep position ──")
        print("  The right finger needs to go between the lids")
        print("  so the lid doesn't fully close.")
        right_prep_wp = record_arm(mc_r, "RIGHT", (0, 255, 255))
        if not right_prep_wp:
            print("  Failed to record right arm prep!")
            return

        # Record right arm's final (prep) position
        right_parked = get_parked_angles(mc_r)

        # Step 2: Left arm close
        print("\n  ── Step 2: LEFT arm closes the lid ──")
        print("  Right arm is locked in prep position.")
        print("  Drag left arm to close the lid.")
        left_close_wp = record_arm(mc_l, "LEFT", (255, 165, 0))
        if not left_close_wp:
            print("  Failed to record left arm close!")
            return

        # Record left arm's final position
        left_parked = get_parked_angles(mc_l)

        # Build close_lid action:
        # Phase 1: right arm moves (left static at its current pos before close)
        # Phase 2: left arm moves (right static at prep pos)
        # Read left arm start pos (whatever it was before we started close recording)
        left_start = left_close_wp[0]  # first recorded position

        close_action = {
            "type": "dual_arm_trajectory",
            "phases": [
                {
                    "name": "right_prep",
                    "active_arm": "right",
                    "right_waypoints": right_prep_wp,
                    "left_waypoints": pad_static(left_start, len(right_prep_wp)),
                },
                {
                    "name": "left_close",
                    "active_arm": "left",
                    "right_waypoints": pad_static(right_parked, len(left_close_wp)),
                    "left_waypoints": left_close_wp,
                },
            ],
            # Flat waypoints for backward compat with replay code
            "right_waypoints": right_prep_wp + pad_static(right_parked, len(left_close_wp)),
            "left_waypoints": pad_static(left_start, len(right_prep_wp)) + left_close_wp,
            "num_waypoints": len(right_prep_wp) + len(left_close_wp),
            "method": "sequential_right_then_left",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        actions["close_lid"] = close_action
        with open(ACTIONS_PATH, "w") as f:
            json.dump(actions, f, indent=2)
        print(f"\n  ✓ Saved 'close_lid' ({close_action['num_waypoints']} waypoints)")

        # Replay test
        test = input("\n  Replay close_lid? (y/n): ").strip().lower()
        if test == "y":
            # Reset — home both arms first
            mc_r.send_angles([0, 0, 0, 0, 0, 0], 20)
            mc_l.send_angles([0, 0, 0, 0, 0, 0], 20)
            time.sleep(3)
            input("  Make sure lid is OPEN, press ENTER...")

            print("\n  Phase 1: Right arm preps...")
            mc_r.set_color(0, 255, 255)
            for wr in right_prep_wp:
                mc_r.send_angles(wr, 25)
                time.sleep(0.4)
            for _ in range(20):
                if not mc_r.is_moving():
                    break
                time.sleep(0.2)
            time.sleep(0.5)

            print("  Phase 2: Left arm closes...")
            mc_l.set_color(255, 165, 0)
            for wl in left_close_wp:
                mc_l.send_angles(wl, 25)
                time.sleep(0.4)
            for _ in range(20):
                if not mc_l.is_moving():
                    break
                time.sleep(0.2)
            time.sleep(0.5)
            print("  Close replay done!")

    # ── TEACH OPEN LID ──
    if choice in ("2", "3"):
        print("\n" + "=" * 55)
        print("  TEACHING: OPEN LID")
        print("  Both arms work together to open the lid.")
        print("=" * 55)

        # Release both arms and record simultaneously
        print("\n  ── Both arms open the lid together ──")
        mc_r.set_color(0, 255, 255)
        mc_l.set_color(0, 255, 255)
        mc_r.release_all_servos()
        mc_l.release_all_servos()
        time.sleep(0.5)

        print("\n  *** BOTH ARMS RELEASED ***")
        print("  Position both arms, then press ENTER to START recording.")
        input("  → ENTER to start recording...")

        print("  *** RECORDING — drag both arms now! ***")
        mc_r.set_color(255, 0, 0)
        mc_l.set_color(255, 0, 0)

        recording = True
        wp_r = []
        wp_l = []

        def record_both():
            while recording:
                a_r = mc_r.get_angles()
                a_l = mc_l.get_angles()
                if (a_r and a_r != -1 and isinstance(a_r, list) and len(a_r) == 6
                        and a_l and a_l != -1 and isinstance(a_l, list) and len(a_l) == 6):
                    wp_r.append([round(v, 2) for v in a_r])
                    wp_l.append([round(v, 2) for v in a_l])
                time.sleep(0.1)

        t = threading.Thread(target=record_both, daemon=True)
        t.start()

        input("  → ENTER to STOP recording...")
        recording = False
        time.sleep(0.3)

        mc_r.focus_all_servos()
        mc_l.focus_all_servos()
        time.sleep(0.5)
        mc_r.set_color(0, 255, 0)
        mc_l.set_color(0, 255, 0)

        print(f"  Recorded {len(wp_r)} raw samples ({len(wp_r)/10:.1f}s)")

        if len(wp_r) < 3:
            print("  Too few waypoints!")
            return

        # Downsample to ~20 waypoints
        step = max(1, len(wp_r) // 20)
        right_open_wp = wp_r[::step]
        left_open_wp = wp_l[::step]
        if wp_r[-1] != right_open_wp[-1]:
            right_open_wp.append(wp_r[-1])
            left_open_wp.append(wp_l[-1])

        print(f"  Downsampled to {len(right_open_wp)} waypoints")

        open_action = {
            "type": "dual_arm_trajectory",
            "right_waypoints": right_open_wp,
            "left_waypoints": left_open_wp,
            "num_waypoints": len(right_open_wp),
            "method": "both_arms",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        actions["open_lid"] = open_action
        with open(ACTIONS_PATH, "w") as f:
            json.dump(actions, f, indent=2)
        print(f"\n  ✓ Saved 'open_lid' ({open_action['num_waypoints']} waypoints)")

        # Replay test
        test = input("\n  Replay open_lid? (y/n): ").strip().lower()
        if test == "y":
            print("\n  Both arms open...")
            mc_r.set_color(0, 255, 0)
            mc_l.set_color(0, 255, 0)
            for wr, wl in zip(right_open_wp, left_open_wp):
                mc_r.send_angles(wr, 25)
                mc_l.send_angles(wl, 25)
                time.sleep(0.4)
            for _ in range(20):
                if not mc_r.is_moving() and not mc_l.is_moving():
                    break
                time.sleep(0.2)
            time.sleep(0.5)
            print("  Open replay done!")

    # Home
    print("\n  Homing both arms...")
    mc_r.send_angles([0, 0, 0, 0, 0, 0], 15)
    mc_l.send_angles([0, 0, 0, 0, 0, 0], 15)
    time.sleep(3)
    mc_r.set_color(255, 255, 255)
    mc_l.set_color(255, 255, 255)
    print("\n  Done!")


if __name__ == "__main__":
    main()
