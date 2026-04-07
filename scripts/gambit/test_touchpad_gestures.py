"""
Touchpad Gesture Test — Left click, Right click, Two-finger scroll.
===================================================================
Uses taught touchpad boundaries from data/touchpad_boundaries.json.

Click zones:
  - Left click:  anywhere except bottom-right quadrant
  - Right click:  bottom-right quadrant only
  - Scroll:       two fingers (both arms) swipe up/down together

Run: python scripts/gambit/test_touchpad_gestures.py
"""
import json
import sys
import time
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.cobot.cached_robot import CachedRobot

RIGHT_IP = "192.168.0.5"
LEFT_IP = "192.168.0.6"
PORT = 9000

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")

# Load touchpad boundaries
with open(os.path.join(DATA_DIR, "touchpad_boundaries.json")) as f:
    TP = json.load(f)

# Extract corner positions and orientations per arm
LEFT_TL = TP["left"]["top_left"]["coords"]      # [x, y, z, rx, ry, rz]
LEFT_BL = TP["left"]["bottom_left"]["coords"]
RIGHT_TR = TP["right"]["top_right"]["coords"]
RIGHT_BR = TP["right"]["bottom_right"]["coords"]

# Touchpad surface Z per arm (average of its two corners)
LEFT_SURFACE_Z = (LEFT_TL[2] + LEFT_BL[2]) / 2
RIGHT_SURFACE_Z = (RIGHT_TR[2] + RIGHT_BR[2]) / 2


def avg_angle(a, b):
    """Average two angles in degrees, handling ±180 wrapping."""
    r = math.atan2(
        math.sin(math.radians(a)) + math.sin(math.radians(b)),
        math.cos(math.radians(a)) + math.cos(math.radians(b)),
    )
    return math.degrees(r)


# Orientation per arm — use angle-safe averaging
LEFT_RX  = avg_angle(LEFT_TL[3], LEFT_BL[3])
LEFT_RY  = avg_angle(LEFT_TL[4], LEFT_BL[4])
LEFT_RZ  = avg_angle(LEFT_TL[5], LEFT_BL[5])

RIGHT_RX = avg_angle(RIGHT_TR[3], RIGHT_BR[3])
RIGHT_RY = avg_angle(RIGHT_TR[4], RIGHT_BR[4])
RIGHT_RZ = avg_angle(RIGHT_TR[5], RIGHT_BR[5])

HOVER_OFFSET = 25       # mm above surface
CLICK_PRESS_MM = 6      # mm below surface for firm click (~150g force)
SCROLL_DISTANCE = 25    # mm to swipe for scroll

# Taught scroll contact points (where user placed the arms for two-finger scroll)
# Left arm taught Z was too deep (42.1 vs surface 47.0) — use surface Z for light contact
L_SCROLL = [254.9, -51.8, LEFT_SURFACE_Z + 9.5, 174.52, 1.9, -109.66]
R_SCROLL = [244.4, 27.3, RIGHT_SURFACE_Z + 4.5, -177.32, 4.08, 16.25]


def lerp(a, b, t):
    """Linear interpolation between two [x, y, z, ...] coords, fraction t."""
    return [a[i] + (b[i] - a[i]) * t for i in range(len(a))]


def wait_still(robot, timeout=2.0):
    deadline = time.time() + timeout
    time.sleep(0.15)
    while time.time() < deadline:
        try:
            if not robot.is_moving():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def left_click(left_robot):
    """Left click: press on the left-center of the touchpad (left arm)."""
    # Target: center of left half (midpoint of top-left and bottom-left)
    target = lerp(LEFT_TL, LEFT_BL, 0.5)  # vertical center
    x, y, z = target[0], target[1], LEFT_SURFACE_Z
    rx, ry, rz = LEFT_RX, LEFT_RY, LEFT_RZ
    hover_z = z + HOVER_OFFSET
    press_z = z - CLICK_PRESS_MM

    print("  Left click: moving to hover...", end="", flush=True)
    left_robot.send_coords([x, y, hover_z, rx, ry, rz], 30, 0)
    wait_still(left_robot)
    print(" pressing...", end="", flush=True)

    # Press down firmly
    left_robot.send_coords([x, y, press_z, rx, ry, rz], 80, 0)
    time.sleep(0.2)

    # Lift
    left_robot.send_coords([x, y, hover_z, rx, ry, rz], 50, 0)
    wait_still(left_robot)
    print(" done!")


def right_click(right_robot):
    """Right click: press firmly at the bottom-right corner."""
    # Use the exact taught BR corner position and orientation
    x, y, z = RIGHT_BR[0], RIGHT_BR[1], RIGHT_BR[2]
    rx, ry, rz = RIGHT_BR[3], RIGHT_BR[4], RIGHT_BR[5]
    hover_z = z + HOVER_OFFSET
    press_z = z - CLICK_PRESS_MM

    print(f"  Right click target: ({x:.1f}, {y:.1f}, {z:.1f})", flush=True)
    print("  Right click: moving to hover...", end="", flush=True)
    right_robot.send_coords([x, y, hover_z, rx, ry, rz], 30, 0)
    wait_still(right_robot)
    print(" pressing...", end="", flush=True)

    # Press down firmly
    right_robot.send_coords([x, y, press_z, rx, ry, rz], 80, 0)
    time.sleep(0.2)

    # Lift
    right_robot.send_coords([x, y, hover_z, rx, ry, rz], 50, 0)
    wait_still(right_robot)
    print(" done!")


def _scroll(left_robot, right_robot, direction):
    """Two-finger scroll using taught contact points.
    direction: 'up' or 'down'.
    Uses exact taught positions/orientations for reliable contact."""
    # Taught start = scroll-up start (near bottom of touchpad)
    lx, ly, lz = L_SCROLL[0], L_SCROLL[1], L_SCROLL[2]
    lrx, lry, lrz = L_SCROLL[3], L_SCROLL[4], L_SCROLL[5]
    rx, ry, rz = R_SCROLL[0], R_SCROLL[1], R_SCROLL[2]
    rrx, rry, rrz = R_SCROLL[3], R_SCROLL[4], R_SCROLL[5]

    l_hover = lz + HOVER_OFFSET
    r_hover = rz + HOVER_OFFSET

    # Direction: left arm top is TL (Y=-0.8), right arm top is TR (Y=-13.9)
    # For scroll up: slide from taught pos toward top
    # For scroll down: start near top, slide toward taught pos
    l_up_dir = 1 if LEFT_TL[1] > LEFT_BL[1] else -1  # +1 = increasing Y is toward top
    r_up_dir = 1 if RIGHT_TR[1] > RIGHT_BR[1] else -1  # -1 = decreasing Y is toward top

    if direction == 'up':
        l_y_start = ly
        l_y_end   = ly + l_up_dir * SCROLL_DISTANCE
        r_y_start = ry
        r_y_end   = ry + r_up_dir * SCROLL_DISTANCE
    else:  # down
        l_y_start = ly + l_up_dir * SCROLL_DISTANCE
        l_y_end   = ly
        r_y_start = ry + r_up_dir * SCROLL_DISTANCE
        r_y_end   = ry

    print(f"  Left:  Y {l_y_start:.1f} \u2192 {l_y_end:.1f}")
    print(f"  Right: Y {r_y_start:.1f} \u2192 {r_y_end:.1f}")

    print(f"  Scroll {direction}: hover...", end="", flush=True)
    left_robot.send_coords([lx, l_y_start, l_hover, lrx, lry, lrz], 30, 0)
    right_robot.send_coords([rx, r_y_start, r_hover, rrx, rry, rrz], 30, 0)
    wait_still(left_robot)
    wait_still(right_robot)
    print(" touch...", end="", flush=True)

    # Touch at taught Z (light contact, no click)
    left_robot.send_coords([lx, l_y_start, lz, lrx, lry, lrz], 15, 0)
    right_robot.send_coords([rx, r_y_start, rz, rrx, rry, rrz], 15, 0)
    wait_still(left_robot)
    wait_still(right_robot)
    time.sleep(0.3)
    print(" slide...", end="", flush=True)

    # Slide at constant Z
    left_robot.send_coords([lx, l_y_end, lz, lrx, lry, lrz], 8, 0)
    right_robot.send_coords([rx, r_y_end, rz, rrx, rry, rrz], 8, 0)
    wait_still(left_robot, timeout=4.0)
    wait_still(right_robot, timeout=4.0)
    print(" lift...", end="", flush=True)

    # Lift
    left_robot.send_coords([lx, l_y_end, l_hover, lrx, lry, lrz], 40, 0)
    right_robot.send_coords([rx, r_y_end, r_hover, rrx, rry, rrz], 40, 0)
    wait_still(left_robot)
    wait_still(right_robot)
    print(" done!")


def scroll_up(left_robot, right_robot):
    _scroll(left_robot, right_robot, 'up')


def scroll_down(left_robot, right_robot):
    _scroll(left_robot, right_robot, 'down')


def main():
    print("╔═══════════════════════════════════════════╗")
    print("║  TOUCHPAD GESTURE TEST                     ║")
    print("╚═══════════════════════════════════════════╝")
    print()
    print(f"  Left surface Z:  {LEFT_SURFACE_Z:.1f} mm")
    print(f"  Right surface Z: {RIGHT_SURFACE_Z:.1f} mm")
    print(f"  Left orient:     ({LEFT_RX:.1f}, {LEFT_RY:.1f}, {LEFT_RZ:.1f})")
    print(f"  Right orient:    ({RIGHT_RX:.1f}, {RIGHT_RY:.1f}, {RIGHT_RZ:.1f})")
    print(f"  Click depth:     {CLICK_PRESS_MM} mm below surface")
    print(f"  Scroll distance: {SCROLL_DISTANCE} mm")

    left = CachedRobot(LEFT_IP, PORT)
    right = CachedRobot(RIGHT_IP, PORT)
    left.power_on()
    right.power_on()
    time.sleep(0.5)

    # 1. Left click
    print("\n── Test 1: LEFT CLICK ──")
    input("  Press ENTER to left-click...")
    left.set_color(0, 255, 0)
    left_click(left)
    left.set_color(255, 255, 255)

    # 2. Right click
    print("\n── Test 2: RIGHT CLICK ──")
    input("  Press ENTER to right-click...")
    right.set_color(255, 0, 0)
    right_click(right)
    right.set_color(255, 255, 255)

    # 3. Scroll up
    print("\n── Test 3: TWO-FINGER SCROLL UP ──")
    input("  Press ENTER to scroll up...")
    left.set_color(0, 0, 255)
    right.set_color(0, 0, 255)
    scroll_up(left, right)
    left.set_color(255, 255, 255)
    right.set_color(255, 255, 255)

    # 4. Scroll down
    print("\n── Test 4: TWO-FINGER SCROLL DOWN ──")
    input("  Press ENTER to scroll down...")
    left.set_color(0, 0, 255)
    right.set_color(0, 0, 255)
    scroll_down(left, right)
    left.set_color(255, 255, 255)
    right.set_color(255, 255, 255)

    print("\n  ✓ All gestures complete!")


if __name__ == "__main__":
    main()
