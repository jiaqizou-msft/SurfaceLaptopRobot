"""
Post-processing and visualization for VLM grounding results.

Takes the VLM bounding-box output and:
  1. Converts normalized (0–999) coords to actual pixel coords
  2. Computes center points
  3. Draws bounding boxes and labels on the image
  4. Saves visualization
"""

import os
import time
import logging
from typing import Dict, Any, Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Normalization factor used by the VLM prompt (0–999 range)
NORM_FACTOR = 999


def process_grounding_result(
    result: Dict[str, Any],
    image_path: str,
    save_viz: bool = True,
    viz_dir: str = "visualizations",
) -> Dict[str, Any]:
    """
    Post-process VLM grounding output.

    Args:
        result: Dict from VLM with keys start, start_xyxy, end, end_xyxy
                (coordinates normalized 0–999)
        image_path: Path to the original overhead image
        save_viz: Whether to save a visualization image
        viz_dir: Directory for visualization images

    Returns:
        Dict with pixel centers and robot-ready info:
        {
            "start_name": str,
            "start_center_px": (u, v),
            "start_bbox_px": [(x1,y1), (x2,y2)],
            "end_name": str,
            "end_center_px": (u, v),
            "end_bbox_px": [(x1,y1), (x2,y2)],
            "viz_path": str or None,
        }
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    img_h, img_w = img.shape[:2]

    # --- Decode start object ---
    start_name = result["start"]
    s_x1 = int(result["start_xyxy"][0][0] * img_w / NORM_FACTOR)
    s_y1 = int(result["start_xyxy"][0][1] * img_h / NORM_FACTOR)
    s_x2 = int(result["start_xyxy"][1][0] * img_w / NORM_FACTOR)
    s_y2 = int(result["start_xyxy"][1][1] * img_h / NORM_FACTOR)
    s_cx = (s_x1 + s_x2) // 2
    s_cy = (s_y1 + s_y2) // 2

    # --- Decode end object ---
    end_name = result["end"]
    e_x1 = int(result["end_xyxy"][0][0] * img_w / NORM_FACTOR)
    e_y1 = int(result["end_xyxy"][0][1] * img_h / NORM_FACTOR)
    e_x2 = int(result["end_xyxy"][1][0] * img_w / NORM_FACTOR)
    e_y2 = int(result["end_xyxy"][1][1] * img_h / NORM_FACTOR)
    e_cx = (e_x1 + e_x2) // 2
    e_cy = (e_y1 + e_y2) // 2

    viz_path = None
    if save_viz:
        viz_path = _draw_visualization(
            img, image_path,
            start_name, (s_x1, s_y1), (s_x2, s_y2), (s_cx, s_cy),
            end_name, (e_x1, e_y1), (e_x2, e_y2), (e_cx, e_cy),
            viz_dir,
        )

    return {
        "start_name": start_name,
        "start_center_px": (s_cx, s_cy),
        "start_bbox_px": [(s_x1, s_y1), (s_x2, s_y2)],
        "end_name": end_name,
        "end_center_px": (e_cx, e_cy),
        "end_bbox_px": [(e_x1, e_y1), (e_x2, e_y2)],
        "viz_path": viz_path,
    }


def process_single_object_result(
    result: Dict[str, Any],
    image_path: str,
) -> Dict[str, Any]:
    """
    Post-process a single-object detection result.

    Returns:
        {
            "object_name": str,
            "center_px": (u, v),
            "bbox_px": [(x1,y1), (x2,y2)],
        }
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    img_h, img_w = img.shape[:2]

    name = result["object"]
    x1 = int(result["xyxy"][0][0] * img_w / NORM_FACTOR)
    y1 = int(result["xyxy"][0][1] * img_h / NORM_FACTOR)
    x2 = int(result["xyxy"][1][0] * img_w / NORM_FACTOR)
    y2 = int(result["xyxy"][1][1] * img_h / NORM_FACTOR)
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    return {
        "object_name": name,
        "center_px": (cx, cy),
        "bbox_px": [(x1, y1), (x2, y2)],
    }


def _draw_visualization(
    img: np.ndarray,
    image_path: str,
    start_name: str, s_tl, s_br, s_center,
    end_name: str, e_tl, e_br, e_center,
    viz_dir: str,
) -> str:
    """Draw bounding boxes, centers, labels, and save visualization."""
    vis = img.copy()

    # Start object — red
    cv2.rectangle(vis, s_tl, s_br, (0, 0, 255), 3)
    cv2.circle(vis, s_center, 6, (0, 0, 255), -1)
    cv2.putText(vis, f"START: {start_name}", (s_tl[0], max(s_tl[1] - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # End object — blue
    cv2.rectangle(vis, e_tl, e_br, (255, 0, 0), 3)
    cv2.circle(vis, e_center, 6, (255, 0, 0), -1)
    cv2.putText(vis, f"END: {end_name}", (e_tl[0], max(e_tl[1] - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    # Arrow from start to end
    cv2.arrowedLine(vis, s_center, e_center, (0, 255, 0), 2, tipLength=0.05)

    # Save to temp
    temp_path = os.path.join(os.path.dirname(image_path), "vl_now_viz.jpg")
    cv2.imwrite(temp_path, vis)

    # Save timestamped copy to visualizations/
    os.makedirs(viz_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    ts_path = os.path.join(viz_dir, f"{ts}.jpg")
    cv2.imwrite(ts_path, vis)

    logger.info(f"Visualization saved to {ts_path}")
    return ts_path
