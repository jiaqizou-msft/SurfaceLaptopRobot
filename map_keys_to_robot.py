"""
Cross-camera correspondence + dual-arm robot mapping.

We have 78 key pixel positions from overhead RealSense annotation.
Now:
1. Get depth from overhead RealSense -> 3D camera frame for each key
2. Drag-teach a few keys per arm -> robot coords  
3. Build pixel->robot affine per arm
4. All 78 keys get robot coords
5. Save the complete dual-arm keyboard layout
"""
from pymycobot import MyCobot280Socket
import pyrealsense2 as rs
import cv2
import numpy as np
import json
import time
import os

os.makedirs("temp", exist_ok=True)

RS_OVERHEAD_SN = "335222075369"
ARMS = {
    "right": {"ip": "10.105.230.93", "port": 9000},
    "left":  {"ip": "10.105.230.94", "port": 9000},
}

# Load annotation
with open("data/keyboard_vision_detected.json") as f:
    anno = json.load(f)
keys = anno["detected_keys"]
print(f"Loaded {len(keys)} key pixel positions from annotation")


def read_robot_stable(mc, retries=12):
    coords_list = []
    for _ in range(retries):
        time.sleep(0.5)
        c = mc.get_coords()
        if c and c != -1 and len(c) >= 6:
            coords_list.append(c[:3])
    if len(coords_list) < 2:
        mc.set_color(0, 255, 0)
        time.sleep(1)
        for _ in range(5):
            time.sleep(0.5)
            c = mc.get_coords()
            if c and c != -1 and len(c) >= 6:
                coords_list.append(c[:3])
    if not coords_list:
        return None
    recent = coords_list[-4:] if len(coords_list) >= 4 else coords_list
    avg = [sum(x)/len(x) for x in zip(*recent)]
    return [round(v, 2) for v in avg]


def teach_arm(arm_name, mc):
    """Drag-teach reference keys for one arm."""
    print(f"\n{'='*55}")
    print(f"  TEACHING: {arm_name.upper()} ARM")
    print(f"{'='*55}")
    print("  Servos released. Drag finger to each key.")
    print("  Type key name + ENTER to record. 'done' to finish.\n")
    
    mc.power_on()
    time.sleep(1)
    mc.release_all_servos()
    time.sleep(1)
    mc.set_color(255, 50, 0 if arm_name == "right" else 255)
    
    taught = {}
    while True:
        try:
            inp = input(f"  [{arm_name}] Key: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not inp:
            continue
        if inp.lower() == "done":
            break
        if inp.lower() == "show":
            for k, v in sorted(taught.items()):
                print(f"    {k}: ({v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f})")
            continue

        key = inp.lower()
        if key not in keys:
            print(f"    '{key}' not in annotation! Available: {', '.join(sorted(keys.keys())[:15])}...")
            continue

        print("    Hold still (reading position)...")
        time.sleep(1)
        coords = read_robot_stable(mc)
        if coords is None:
            print("    FAILED to read position!")
            continue
        taught[key] = coords
        px = keys[key]["pixel"]
        print(f"    Recorded '{key}': robot=({coords[0]:.1f},{coords[1]:.1f},{coords[2]:.1f}), pixel=({px[0]},{px[1]})")

    mc.focus_all_servos()
    time.sleep(0.5)
    mc.set_color(255, 255, 255)
    return taught


def build_pixel_to_robot(taught, keys_data):
    """Build pixel->robot affine from taught key correspondences.
    Each taught key has: pixel (from annotation) + robot coords (from teaching).
    """
    A, B = [], []
    for key, robot_xyz in taught.items():
        if key in keys_data:
            px, py = keys_data[key]["pixel"]
            A.append([px, py, 1])
            B.append([robot_xyz[0], robot_xyz[1]])
    
    A = np.array(A, dtype=float)
    B = np.array(B, dtype=float)
    
    if len(A) < 3:
        print(f"  Only {len(A)} correspondences, need 3+")
        return None, None

    M, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
    
    # Verify
    pred = A @ M
    errors = np.sqrt(np.sum((pred - B)**2, axis=1))
    print(f"  Pixel->Robot affine: {len(A)} points, mean error={np.mean(errors):.1f}mm")
    
    # Get the Z from taught keys
    z_values = [v[2] for v in taught.values()]
    kbd_z = float(np.median(z_values))
    
    return M, kbd_z


def compute_all_robot_coords(M, kbd_z, keys_data, arm_name):
    """Apply pixel->robot affine to all keys."""
    result = {}
    for key, kd in keys_data.items():
        px, py = kd["pixel"]
        robot_xy = np.array([px, py, 1]) @ M
        rx, ry = float(robot_xy[0]), float(robot_xy[1])
        reachable = -281 <= rx <= 281 and -200 <= ry <= 200
        result[key] = {
            "pixel": kd["pixel"],
            "mm": kd.get("mm", [0, 0]),
            "robot": [round(rx, 2), round(ry, 2), kbd_z],
            "arm": arm_name,
            "reachable": reachable,
        }
    return result


# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    # Connect arms
    print("Connecting arms...")
    mc_right = MyCobot280Socket(ARMS["right"]["ip"], ARMS["right"]["port"])
    time.sleep(1)
    mc_left = MyCobot280Socket(ARMS["left"]["ip"], ARMS["left"]["port"])
    time.sleep(1)
    
    arm_data = {}
    
    # Teach each arm
    if "--right" in sys.argv or "--both" in sys.argv or len([a for a in sys.argv if a.startswith("--")]) == 0:
        taught_right = teach_arm("right", mc_right)
        if taught_right:
            M_r, z_r = build_pixel_to_robot(taught_right, keys)
            if M_r is not None:
                right_keys = compute_all_robot_coords(M_r, z_r, keys, "right")
                arm_data["right"] = {
                    "affine": M_r.tolist(),
                    "kbd_z": z_r,
                    "taught": {k: list(v) for k, v in taught_right.items()},
                    "keys": right_keys,
                }
                reachable = sum(1 for v in right_keys.values() if v["reachable"])
                print(f"  Right arm: {reachable} reachable keys")
    
    if "--left" in sys.argv or "--both" in sys.argv or len([a for a in sys.argv if a.startswith("--")]) == 0:
        taught_left = teach_arm("left", mc_left)
        if taught_left:
            M_l, z_l = build_pixel_to_robot(taught_left, keys)
            if M_l is not None:
                left_keys = compute_all_robot_coords(M_l, z_l, keys, "left")
                arm_data["left"] = {
                    "affine": M_l.tolist(),
                    "kbd_z": z_l,
                    "taught": {k: list(v) for k, v in taught_left.items()},
                    "keys": left_keys,
                }
                reachable = sum(1 for v in left_keys.values() if v["reachable"])
                print(f"  Left arm: {reachable} reachable keys")
    
    # Merge: assign each key to the best arm
    merged = {}
    for arm_name, ad in arm_data.items():
        for key, kd in ad["keys"].items():
            if not kd["reachable"]:
                continue
            if key not in merged:
                merged[key] = kd
            else:
                # Prefer the arm where the key is more central
                existing_x = abs(merged[key]["robot"][0])
                new_x = abs(kd["robot"][0])
                if new_x < existing_x:
                    merged[key] = kd
    
    # Save
    output = {
        "arms": arm_data,
        "merged_keys": merged,
        "num_merged": len(merged),
        "annotation_source": "data/keyboard_vision_detected.json",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open("data/keyboard_dual_arm.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    # Also update keyboard_taught.json for press_key.py compatibility
    taught_compat = {"keys": {}, "keyboard_z": 0}
    for key, kd in merged.items():
        taught_compat["keys"][key] = {
            "coords": kd["robot"] + [0, 180, 90],
            "arm": kd["arm"],
            "source": "vision_mapped",
        }
    taught_compat["keyboard_z"] = list(arm_data.values())[0]["kbd_z"] if arm_data else 130
    with open("data/keyboard_taught.json", "w") as f:
        json.dump(taught_compat, f, indent=2)
    
    # Home both arms
    mc_right.send_angles([0, 0, 0, 0, 0, 0], 15)
    mc_left.send_angles([0, 0, 0, 0, 0, 0], 15)
    time.sleep(3)
    
    # Summary
    print(f"\n{'='*55}")
    print(f"  COMPLETE: {len(merged)} keys mapped across both arms")
    print(f"{'='*55}")
    left_keys_merged = [k for k, v in merged.items() if v["arm"] == "left"]
    right_keys_merged = [k for k, v in merged.items() if v["arm"] == "right"]
    print(f"  Left arm:  {len(left_keys_merged)} keys")
    print(f"  Right arm: {len(right_keys_merged)} keys")
    print(f"\nSaved to data/keyboard_dual_arm.json + data/keyboard_taught.json")
    print(f"Test with: python press_key_dual.py --fast hello")
