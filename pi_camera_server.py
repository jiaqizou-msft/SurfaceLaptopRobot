#!/usr/bin/env python3
"""
Lightweight MJPEG camera streaming server for Raspberry Pi.

Deploy this script ON the Raspberry Pi (the robot's onboard computer).
It serves the camera feed as an MJPEG stream over HTTP so the Windows
laptop can grab frames remotely.

Endpoints:
    GET /video     — MJPEG stream (for cv2.VideoCapture)
    GET /snapshot  — Single JPEG frame
    GET /          — Simple status page

Usage on the Pi:
    python3 pi_camera_server.py                    # default port 8080
    python3 pi_camera_server.py --port 8080        # custom port
    python3 pi_camera_server.py --camera 0         # camera index
"""

import argparse
import time
import threading

import cv2
from flask import Flask, Response, jsonify

app = Flask(__name__)

# Global camera and frame lock
camera = None
latest_frame = None
frame_lock = threading.Lock()


def camera_capture_loop(camera_index: int):
    """Background thread: continuously capture frames from the camera."""
    global camera, latest_frame

    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        print(f"ERROR: Cannot open camera {camera_index}")
        return

    print(f"Camera {camera_index} opened successfully.")
    while True:
        ret, frame = camera.read()
        if ret:
            with frame_lock:
                latest_frame = frame
        time.sleep(0.03)  # ~30 fps


def generate_mjpeg():
    """Generator: yield MJPEG frames for streaming."""
    while True:
        with frame_lock:
            frame = latest_frame

        if frame is not None:
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )
        time.sleep(0.033)  # ~30 fps


@app.route("/video")
def video_feed():
    """MJPEG video stream endpoint."""
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/snapshot")
def snapshot():
    """Single JPEG snapshot endpoint."""
    with frame_lock:
        frame = latest_frame

    if frame is None:
        return "No frame available", 503

    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return Response(jpeg.tobytes(), mimetype="image/jpeg")


@app.route("/")
def index():
    """Status page."""
    return jsonify({
        "service": "myCobot Pi Camera Server",
        "status": "running",
        "endpoints": {
            "/video": "MJPEG stream",
            "/snapshot": "Single JPEG frame",
        },
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pi Camera MJPEG Server")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default 8080)")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0)")
    args = parser.parse_args()

    # Start camera capture in background thread
    cam_thread = threading.Thread(
        target=camera_capture_loop,
        args=(args.camera,),
        daemon=True,
    )
    cam_thread.start()
    time.sleep(1)  # Let camera initialize

    print(f"Starting camera server on {args.host}:{args.port}")
    print(f"  Stream:   http://{args.host}:{args.port}/video")
    print(f"  Snapshot: http://{args.host}:{args.port}/snapshot")

    app.run(host=args.host, port=args.port, threaded=True)
