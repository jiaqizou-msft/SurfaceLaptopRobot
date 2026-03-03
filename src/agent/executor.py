"""
Agent executor — safe dispatch of planned actions.

Instead of eval(), we use a dispatch table mapping function names
to actual Python callables.
"""

import re
import time
import logging
from typing import Dict, Any, Callable, List

from src.cobot import actions
from src.vlm import pipeline
from src.agent.planner import get_planner

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Dispatch table: function name → callable
# ──────────────────────────────────────────────────────────────────────────────

DISPATCH: Dict[str, Callable] = {
    # Motion
    "back_zero": actions.back_zero,
    "move_to_coords": actions.move_to_coords,
    "send_angles": actions.send_angles,
    "send_angle": actions.send_angle,
    "send_coords": actions.send_coords,
    "move_to_top_view": actions.move_to_top_view,
    "finger_touch": actions.finger_touch,
    "finger_move": actions.finger_move,
    "jog_angle": actions.jog_angle,
    "jog_coord": actions.jog_coord,
    "jog_increment_angle": actions.jog_increment_angle,
    "jog_increment_coord": actions.jog_increment_coord,
    "pause_motion": actions.pause_motion,
    "resume_motion": actions.resume_motion,
    "stop_motion": actions.stop_motion,

    # Status
    "get_angles": actions.get_angles,
    "get_coords": actions.get_coords,
    "get_robot_status": actions.get_robot_status,
    "is_moving": actions.is_moving,

    # System
    "power_on": actions.power_on,
    "power_off": actions.power_off,
    "release_all_servos": actions.release_all_servos,
    "focus_all_servos": actions.focus_all_servos,
    "set_led_color": actions.set_led_color,

    # Gestures
    "head_shake": actions.head_shake,
    "head_nod": actions.head_nod,
    "head_dance": actions.head_dance,

    # VLM pipelines
    "vlm_move": pipeline.vlm_move,
    "vlm_touch": pipeline.vlm_touch,
    "vlm_vqa": pipeline.vlm_vqa,
    "llm_led": pipeline.llm_led,
    "capture_image": pipeline.capture_image,

    # Utility
    "wait": lambda seconds: time.sleep(float(seconds)),
    "time.sleep": lambda seconds: time.sleep(float(seconds)),
}


def _parse_function_call(call_str: str):
    """
    Parse a function call string like 'move_to_coords(150, -120)'
    into (function_name, args, kwargs).
    """
    # Match: func_name(args...)
    match = re.match(r"(\w[\w.]*)\s*\((.*)\)$", call_str.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"Cannot parse function call: {call_str}")

    func_name = match.group(1)
    args_str = match.group(2).strip()

    if not args_str:
        return func_name, [], {}

    # Parse arguments safely using ast.literal_eval for each arg
    import ast
    args = []
    kwargs = {}

    # Split on commas, but respect brackets and quotes
    # Use a simple state machine
    parts = _split_args(args_str)
    for part in parts:
        part = part.strip()
        if "=" in part and not part.startswith("'") and not part.startswith('"'):
            # Check if it's a kwarg (key=value)
            eq_idx = part.index("=")
            key = part[:eq_idx].strip()
            val = part[eq_idx + 1:].strip()
            try:
                kwargs[key] = ast.literal_eval(val)
            except (ValueError, SyntaxError):
                kwargs[key] = val
        else:
            try:
                args.append(ast.literal_eval(part))
            except (ValueError, SyntaxError):
                args.append(part)

    return func_name, args, kwargs


def _split_args(s: str) -> List[str]:
    """Split argument string on commas, respecting brackets and quotes."""
    parts = []
    depth = 0
    current = ""
    in_string = None

    for ch in s:
        if in_string:
            current += ch
            if ch == in_string:
                in_string = None
        elif ch in ('"', "'"):
            current += ch
            in_string = ch
        elif ch in ("(", "[", "{"):
            current += ch
            depth += 1
        elif ch in (")", "]", "}"):
            current += ch
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch

    if current.strip():
        parts.append(current)

    return parts


def execute_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a plan produced by the AgentPlanner.

    Args:
        plan: {"function": ["func1()", ...], "response": "..."}

    Returns:
        {"response": "...", "results": [...], "errors": [...]}
    """
    functions = plan.get("function", [])
    response = plan.get("response", "")
    results = []
    errors = []

    for call_str in functions:
        try:
            func_name, args, kwargs = _parse_function_call(call_str)
            if func_name not in DISPATCH:
                err = f"Unknown function: {func_name}"
                logger.warning(err)
                errors.append(err)
                continue

            logger.info(f"Executing: {call_str}")
            result = DISPATCH[func_name](*args, **kwargs)
            results.append({"call": call_str, "result": str(result)})
            logger.info(f"Result: {result}")

        except Exception as e:
            err = f"Error executing '{call_str}': {e}"
            logger.error(err)
            errors.append(err)

    return {
        "response": response,
        "results": results,
        "errors": errors,
    }


def run_agent(instruction: str) -> Dict[str, Any]:
    """
    End-to-end: take a user instruction → plan → execute → return results.
    """
    planner = get_planner()
    plan = planner.plan(instruction)
    logger.info(f"Agent plan: {plan}")
    execution_result = execute_plan(plan)
    return execution_result
