"""
Camera client for capturing frames from the Raspberry Pi camera.

The Pi runs a lightweight MJPEG streaming server (pi_camera_server.py).
This module connects to that stream and provides frame capture utilities.
"""

import os
import time
import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from src.cobot.config import get_config

logger = logging.getLogger(__name__)


class CameraClient:
    """
    Captures frames from the Pi's MJPEG stream over HTTP.
    Also supports a direct snapshot endpoint for single-frame grabs.
    """

    def __init__(self, stream_url: str = None, snapshot_url: str = None):
        cfg = get_config().camera
        self.stream_url = stream_url or cfg.stream_url
        self.snapshot_url = snapshot_url or cfg.snapshot_url
        self.save_dir = cfg.save_dir
        self._cap: Optional[cv2.VideoCapture] = None

    def open_stream(self) -> bool:
        """Open the MJPEG video stream."""
        if self._cap is not None and self._cap.isOpened():
            return True
        self._cap = cv2.VideoCapture(self.stream_url)
        if not self._cap.isOpened():
            logger.error(f"Failed to open camera stream: {self.stream_url}")
            return False
        logger.info(f"Camera stream opened: {self.stream_url}")
        return True

    def close_stream(self):
        """Release the video capture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Camera stream closed.")

    def grab_frame(self) -> Optional[np.ndarray]:
        """
        Grab a single frame from the stream.
        Returns BGR numpy array or None on failure.
        """
        if not self.open_stream():
            return None
        # Read a few frames to flush the buffer and get a fresh one
        for _ in range(3):
            ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.error("Failed to grab frame from stream.")
            return None
        return frame

    def capture_snapshot(self, filename: str = "vl_now.jpg") -> Optional[str]:
        """
        Capture a single frame and save it to disk.

        Returns:
            Absolute path to the saved image, or None on failure.
        """
        import httpx

        save_path = os.path.join(self.save_dir, filename)
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)

        # Try the snapshot endpoint first (faster, single JPEG)
        try:
            resp = httpx.get(self.snapshot_url, timeout=5.0)
            if resp.status_code == 200:
                img_array = np.frombuffer(resp.content, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if frame is not None:
                    cv2.imwrite(save_path, frame)
                    logger.info(f"Snapshot saved to {save_path}")
                    return os.path.abspath(save_path)
        except Exception as e:
            logger.warning(f"Snapshot endpoint failed ({e}), falling back to stream.")

        # Fallback: grab from MJPEG stream
        frame = self.grab_frame()
        if frame is not None:
            cv2.imwrite(save_path, frame)
            logger.info(f"Snapshot saved to {save_path} (via stream)")
            return os.path.abspath(save_path)

        logger.error("Failed to capture snapshot.")
        return None

    def get_frame_base64(self) -> Optional[str]:
        """Capture a frame and return it as a base64-encoded JPEG string."""
        import base64

        frame = self.grab_frame()
        if frame is None:
            return None
        _, buffer = cv2.imencode(".jpg", frame)
        return base64.b64encode(buffer).decode("utf-8")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_camera: Optional[CameraClient] = None


def get_camera() -> CameraClient:
    global _camera
    if _camera is None:
        _camera = CameraClient()
    return _camera
