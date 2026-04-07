"""
Live Camera Feed — Shows both cameras side-by-side in a window.
Run alongside demo_showcase_loop.py to monitor the robot.

Usage: python scripts/gambit/live_camera_feed.py
Press 'q' to quit.
"""
import cv2
import numpy as np

CAMERA_IDS = [1, 2]
FLIP_CAMS = {1}
GAMMA = 1.4
WINDOW_NAME = "Live Camera Feed (press q to quit)"

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
    else:
        print(f"Camera {cid}: FAILED")

if not caps:
    print("No cameras available!")
    exit(1)

cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, 1280, 480)

print(f"Showing {len(caps)} cameras. Press 'q' to quit.")

while True:
    frames = []
    for cid, cap in caps.items():
        ret, frame = cap.read()
        if ret:
            if cid in FLIP_CAMS:
                frame = cv2.flip(frame, -1)
            frame = cv2.resize(frame, (640, 480))
            frame = cv2.LUT(frame, lut)
            # Add camera label
            label = "Overhead" if cid == 1 else "Front"
            cv2.putText(frame, f"Cam {cid} ({label})", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            frames.append(frame)

    if frames:
        combined = np.hstack(frames) if len(frames) > 1 else frames[0]
        cv2.imshow(WINDOW_NAME, combined)

    key = cv2.waitKey(30) & 0xFF
    if key == ord('q'):
        break

for cap in caps.values():
    cap.release()
cv2.destroyAllWindows()
print("Feed closed.")
