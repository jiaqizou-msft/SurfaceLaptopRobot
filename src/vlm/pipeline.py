"""
VLM-driven motion pipelines.

High-level orchestrations that combine:
  camera capture → VLM grounding → eye2hand calibration → robot motion
"""

import time
import logging
from typing import Dict, Any, Optional

from src.cobot.actions import (
    back_zero, move_to_top_view, finger_touch, finger_move,
    move_to_coords, send_angles, set_led_color, get_mc,
)
from src.cobot.camera import get_camera
from src.vlm.vlm_client import get_vlm_client
from src.vlm.grounding import process_grounding_result, process_single_object_result
from src.calibration.eye2hand import get_eye2hand
from src.cobot.config import get_config

logger = logging.getLogger(__name__)


def vlm_move(instruction: str, retries: int = 3) -> str:
    """
    Full VLM-driven move pipeline:
      1. Move to top-view position
      2. Capture overhead image
      3. Send image + instruction to VLM for object grounding
      4. Post-process bounding boxes → pixel centers
      5. Eye-to-hand calibration → robot XY
      6. Execute finger slide from start to end

    Args:
        instruction: Natural language (e.g. "push the red block to the star")
        retries: Number of VLM call retries on failure

    Returns:
        Status message
    """
    logger.info(f"VLM Move pipeline started: '{instruction}'")

    # Step 1: Go home first
    back_zero(speed=50)

    # Step 2: Move to top-view
    move_to_top_view()
    time.sleep(1)

    # Step 3: Capture overhead image
    camera = get_camera()
    img_path = camera.capture_snapshot("vl_now.jpg")
    if img_path is None:
        return "Error: failed to capture overhead image."

    # Step 4: Call VLM for grounding
    vlm = get_vlm_client()
    result = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"VLM grounding attempt {attempt}/{retries}")
            result = vlm.ground_objects(instruction, img_path)
            logger.info(f"VLM result: {result}")
            break
        except Exception as e:
            logger.warning(f"VLM attempt {attempt} failed: {e}")
            if attempt == retries:
                return f"Error: VLM grounding failed after {retries} attempts: {e}"

    # Step 5: Post-process → pixel centers
    processed = process_grounding_result(result, img_path)
    start_px = processed["start_center_px"]
    end_px = processed["end_center_px"]
    logger.info(f"Start pixel: {start_px}, End pixel: {end_px}")

    # Step 6: Eye-to-hand calibration → robot coords
    e2h = get_eye2hand()
    start_x, start_y = e2h.pixel_to_robot(start_px[0], start_px[1])
    end_x, end_y = e2h.pixel_to_robot(end_px[0], end_px[1])
    logger.info(f"Start robot: ({start_x}, {start_y}), End robot: ({end_x}, {end_y})")

    # Step 7: Execute the finger slide
    result_msg = finger_move(start_x, start_y, end_x, end_y)

    # Step 8: Return home
    back_zero()

    return (
        f"VLM Move complete. "
        f"Moved '{processed['start_name']}' → '{processed['end_name']}'. "
        f"Start=({start_x:.1f},{start_y:.1f}), End=({end_x:.1f},{end_y:.1f}). "
        f"{result_msg}"
    )


def vlm_touch(description: str, retries: int = 3) -> str:
    """
    VLM-driven single-object touch:
      1. Capture overhead image
      2. Detect the described object
      3. Eye-to-hand → robot XY
      4. Finger touch at that point

    Args:
        description: What object to touch (e.g. "the green ball")
    """
    logger.info(f"VLM Touch pipeline: '{description}'")

    back_zero(speed=50)
    move_to_top_view()
    time.sleep(1)

    camera = get_camera()
    img_path = camera.capture_snapshot("vl_now.jpg")
    if img_path is None:
        return "Error: failed to capture image."

    vlm = get_vlm_client()
    result = None
    for attempt in range(1, retries + 1):
        try:
            result = vlm.detect_single_object(description, img_path)
            break
        except Exception as e:
            logger.warning(f"VLM attempt {attempt} failed: {e}")
            if attempt == retries:
                return f"Error: VLM detection failed: {e}"

    processed = process_single_object_result(result, img_path)
    px = processed["center_px"]

    e2h = get_eye2hand()
    x, y = e2h.pixel_to_robot(px[0], px[1])
    logger.info(f"Touch target: ({x:.1f}, {y:.1f})")

    touch_result = finger_touch(x, y)
    back_zero()

    return f"Touched '{processed['object_name']}' at ({x:.1f}, {y:.1f}). {touch_result}"


def vlm_vqa(question: str) -> str:
    """
    Visual QA pipeline:
      1. Move to top-view and capture image
      2. Send to VLM with the question
      3. Return the answer

    Args:
        question: What to ask about the workspace
    """
    logger.info(f"VLM VQA pipeline: '{question}'")

    back_zero(speed=50)
    move_to_top_view()
    time.sleep(1)

    camera = get_camera()
    img_path = camera.capture_snapshot("vl_now.jpg")
    if img_path is None:
        return "Error: failed to capture image."

    vlm = get_vlm_client()
    answer = vlm.visual_qa(question, img_path)
    return answer


def llm_led(description: str) -> str:
    """
    Use LLM to convert a color description to RGB and set the LED.
    e.g. "ocean sunset" → warm orange → set_led_color(255, 100, 30)
    """
    vlm = get_vlm_client()
    try:
        rgb = vlm.determine_led_color(description)
        set_led_color(rgb[0], rgb[1], rgb[2])
        return f"LED set to {description} → RGB{rgb}"
    except Exception as e:
        return f"Error setting LED color: {e}"


def capture_image() -> str:
    """Move to top-view and capture an overhead image."""
    move_to_top_view()
    time.sleep(1)
    camera = get_camera()
    path = camera.capture_snapshot("vl_now.jpg")
    if path:
        return f"Image captured and saved to {path}"
    return "Error: failed to capture image."
