"""
Intel RealSense D435i integration for the myCobot 280 system.

The RealSense provides:
  - High-quality RGB images (for VLM grounding)
  - Aligned depth maps (for pixel → 3D point deprojection)
  - IMU data (for orientation tracking)

With depth, we can directly compute 3D points in camera frame from any pixel.
Combined with a camera-to-robot rigid transform, this gives us accurate
robot workspace coordinates without the fragile eye-to-hand interpolation.

Architecture:
  RealSense D435i (USB to laptop)  →  color + depth frames
  pixel (u,v) + depth(u,v) → 3D point in camera frame
  camera_to_robot transform → 3D point in robot base frame
"""

import time
import logging
import os
from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import cv2

try:
    import pyrealsense2 as rs
    HAS_REALSENSE = True
except ImportError:
    HAS_REALSENSE = False

logger = logging.getLogger(__name__)


class RealSenseCamera:
    """
    Intel RealSense D435i wrapper providing:
      - Aligned color + depth capture
      - Pixel → 3D deprojection (camera frame)
      - Pixel → robot frame (with extrinsic calibration)
      - Depth-at-point queries
      - Point cloud generation
    """

    def __init__(self, width=640, height=480, fps=30):
        if not HAS_REALSENSE:
            raise RuntimeError("pyrealsense2 not installed. Run: pip install pyrealsense2")

        self.width = width
        self.height = height
        self.fps = fps

        self._pipeline: Optional[rs.pipeline] = None
        self._align: Optional[rs.align] = None
        self._intrinsics: Optional[rs.intrinsics] = None
        self._depth_scale: float = 0.001  # default 1mm

        # Camera-to-robot extrinsic transform (4x4 homogeneous matrix)
        # Set via calibrate_extrinsics()
        self._cam_to_robot: Optional[np.ndarray] = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self):
        """Start the RealSense pipeline."""
        self._pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
        config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)

        profile = self._pipeline.start(config)

        # Depth scale
        depth_sensor = profile.get_device().first_depth_sensor()
        self._depth_scale = depth_sensor.get_depth_scale()

        # Enable high-accuracy preset if available
        if depth_sensor.supports(rs.option.visual_preset):
            depth_sensor.set_option(rs.option.visual_preset, 3)  # High Accuracy

        # Color intrinsics
        color_profile = profile.get_stream(rs.stream.color)
        self._intrinsics = color_profile.as_video_stream_profile().get_intrinsics()

        # Align depth to color
        self._align = rs.align(rs.stream.color)

        # Let auto-exposure settle
        for _ in range(30):
            self._pipeline.wait_for_frames()

        logger.info(f"RealSense started: {self.width}x{self.height}@{self.fps}fps, "
                     f"depth_scale={self._depth_scale}")

    def stop(self):
        """Stop the pipeline."""
        if self._pipeline:
            self._pipeline.stop()
            self._pipeline = None
            logger.info("RealSense stopped.")

    def is_running(self) -> bool:
        return self._pipeline is not None

    # ── Frame Capture ────────────────────────────────────────────────────

    def capture(self) -> Tuple[np.ndarray, np.ndarray, Any]:
        """
        Capture aligned color + depth frames.

        Returns:
            (color_bgr, depth_mm, depth_frame)
            - color_bgr: (H, W, 3) uint8 BGR image
            - depth_mm: (H, W) uint16 depth in millimeters
            - depth_frame: raw rs2 depth frame (for deprojection)
        """
        if not self._pipeline:
            self.start()

        frames = self._pipeline.wait_for_frames()
        aligned = self._align.process(frames)

        color_frame = aligned.get_color_frame()
        depth_frame = aligned.get_depth_frame()

        # Apply temporal + spatial filtering for cleaner depth
        spatial = rs.spatial_filter()
        temporal = rs.temporal_filter()
        depth_frame = spatial.process(depth_frame)
        depth_frame = temporal.process(depth_frame)

        color_image = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame.get_data())

        return color_image, depth_image, depth_frame

    def capture_snapshot(self, filename="temp/rs_snapshot.jpg") -> Optional[str]:
        """Capture color image and save to disk."""
        color, depth, _ = self.capture()
        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
        cv2.imwrite(filename, color)

        # Also save depth colormap
        depth_path = filename.replace(".jpg", "_depth.jpg")
        depth_cm = cv2.applyColorMap(cv2.convertScaleAbs(depth, alpha=0.03), cv2.COLORMAP_JET)
        cv2.imwrite(depth_path, depth_cm)

        return os.path.abspath(filename)

    def get_color_base64(self) -> Optional[str]:
        """Capture color frame and return as base64 JPEG."""
        import base64
        color, _, _ = self.capture()
        _, buffer = cv2.imencode(".jpg", color)
        return base64.b64encode(buffer).decode("utf-8")

    # ── Depth Queries ────────────────────────────────────────────────────

    def get_depth_at(self, u: int, v: int) -> float:
        """
        Get depth at pixel (u, v) in meters.
        Uses a small neighborhood average for robustness.
        """
        _, depth_mm, _ = self.capture()
        return self._robust_depth(depth_mm, u, v)

    def _robust_depth(self, depth_mm: np.ndarray, u: int, v: int, radius: int = 3) -> float:
        """Get robust depth at (u,v) by averaging a small window, ignoring zeros."""
        h, w = depth_mm.shape
        u = max(radius, min(w - radius - 1, u))
        v = max(radius, min(h - radius - 1, v))

        patch = depth_mm[v - radius:v + radius + 1, u - radius:u + radius + 1]
        valid = patch[patch > 0].astype(float)

        if len(valid) == 0:
            return 0.0

        return float(np.median(valid)) * self._depth_scale  # meters

    # ── 3D Deprojection ──────────────────────────────────────────────────

    def pixel_to_3d_camera(self, u: int, v: int, depth_m: float = None) -> Tuple[float, float, float]:
        """
        Deproject pixel (u,v) to 3D point in camera frame (meters).
        If depth_m is None, captures a new frame and reads depth at (u,v).
        """
        if depth_m is None:
            depth_m = self.get_depth_at(u, v)

        if depth_m <= 0:
            raise ValueError(f"No valid depth at pixel ({u},{v})")

        point = rs.rs2_deproject_pixel_to_point(self._intrinsics, [u, v], depth_m)
        return (point[0], point[1], point[2])  # x, y, z in meters

    def pixel_to_3d_robot(self, u: int, v: int, depth_m: float = None) -> Tuple[float, float, float]:
        """
        Deproject pixel (u,v) to 3D point in robot base frame (mm).
        Requires extrinsic calibration (camera-to-robot transform).
        """
        if self._cam_to_robot is None:
            raise RuntimeError("Extrinsic calibration not set. Call calibrate_extrinsics() first.")

        cam_pt = self.pixel_to_3d_camera(u, v, depth_m)
        cam_pt_m = np.array([cam_pt[0], cam_pt[1], cam_pt[2], 1.0])

        robot_pt = self._cam_to_robot @ cam_pt_m
        # Convert to mm
        return (robot_pt[0] * 1000, robot_pt[1] * 1000, robot_pt[2] * 1000)

    # ── Extrinsic Calibration ────────────────────────────────────────────

    def calibrate_extrinsics(
        self,
        camera_points_m: List[Tuple[float, float, float]],
        robot_points_mm: List[Tuple[float, float, float]],
    ) -> np.ndarray:
        """
        Compute the camera-to-robot rigid transform from corresponding 3D point pairs.

        Args:
            camera_points_m: 3D points in camera frame (meters) — from pixel_to_3d_camera()
            robot_points_mm: 3D points in robot frame (mm) — from robot get_coords()

        Returns:
            4x4 homogeneous transformation matrix (camera→robot)
        """
        n = len(camera_points_m)
        if n < 3:
            raise ValueError("Need at least 3 point pairs for rigid transform.")

        # Convert robot points from mm to meters for consistent units
        cam_pts = np.array(camera_points_m)
        rob_pts = np.array(robot_points_mm) / 1000.0

        # Centroid
        cam_centroid = cam_pts.mean(axis=0)
        rob_centroid = rob_pts.mean(axis=0)

        # Center the points
        cam_centered = cam_pts - cam_centroid
        rob_centered = rob_pts - rob_centroid

        # SVD for optimal rotation
        H = cam_centered.T @ rob_centered
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T

        # Ensure proper rotation (det = +1)
        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1
            R = Vt.T @ U.T

        # Translation
        t = rob_centroid - R @ cam_centroid

        # Build 4x4 homogeneous matrix
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = t

        self._cam_to_robot = T
        logger.info(f"Extrinsic calibration computed from {n} points.")
        return T

    def set_extrinsics(self, transform_4x4: np.ndarray):
        """Manually set the camera-to-robot transform."""
        self._cam_to_robot = np.array(transform_4x4)

    def get_extrinsics(self) -> Optional[np.ndarray]:
        """Get the current camera-to-robot transform."""
        return self._cam_to_robot

    def get_intrinsics_dict(self) -> Dict[str, Any]:
        """Get camera intrinsics as a dict."""
        if self._intrinsics is None:
            return {}
        return {
            "width": self._intrinsics.width,
            "height": self._intrinsics.height,
            "fx": self._intrinsics.fx,
            "fy": self._intrinsics.fy,
            "ppx": self._intrinsics.ppx,
            "ppy": self._intrinsics.ppy,
            "model": str(self._intrinsics.model),
            "depth_scale": self._depth_scale,
        }

    # ── Utility ──────────────────────────────────────────────────────────

    def get_workspace_depth_stats(self, roi=None) -> Dict[str, float]:
        """
        Get depth statistics for the workspace.
        roi: (x, y, w, h) region of interest, or None for full frame.
        """
        _, depth_mm, _ = self.capture()
        if roi:
            x, y, w, h = roi
            depth_mm = depth_mm[y:y+h, x:x+w]
        valid = depth_mm[depth_mm > 0].astype(float) * self._depth_scale * 1000
        if len(valid) == 0:
            return {"min": 0, "max": 0, "mean": 0, "coverage": 0}
        return {
            "min_mm": float(valid.min()),
            "max_mm": float(valid.max()),
            "mean_mm": float(valid.mean()),
            "coverage_pct": float(len(valid)) / depth_mm.size * 100,
        }

    def save_calibration(self, path="calibration_realsense.json"):
        """Save extrinsic calibration to JSON."""
        import json
        data = {
            "cam_to_robot_4x4": self._cam_to_robot.tolist() if self._cam_to_robot is not None else None,
            "intrinsics": self.get_intrinsics_dict(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Calibration saved to {path}")

    def load_calibration(self, path="calibration_realsense.json"):
        """Load extrinsic calibration from JSON."""
        import json
        with open(path, "r") as f:
            data = json.load(f)
        if data.get("cam_to_robot_4x4"):
            self._cam_to_robot = np.array(data["cam_to_robot_4x4"])
            logger.info(f"Calibration loaded from {path}")


# ── Singleton ────────────────────────────────────────────────────────────
_realsense: Optional[RealSenseCamera] = None


def get_realsense() -> RealSenseCamera:
    """Get the global RealSense camera singleton."""
    global _realsense
    if _realsense is None:
        _realsense = RealSenseCamera()
    if not _realsense.is_running():
        _realsense.start()
    return _realsense
