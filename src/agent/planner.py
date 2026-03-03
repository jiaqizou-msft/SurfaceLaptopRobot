"""
LLM-based Agent Planner for the myCobot 280.

Takes a natural language instruction and produces a plan of atomic actions.
Uses Azure OpenAI GPT-4o as the planning LLM with function-calling style output.
"""

import json
import logging
from typing import Dict, Any, List, Optional

from openai import AzureOpenAI

from src.cobot.config import get_config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Agent system prompt — defines the action space and output format
# ──────────────────────────────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = """You are an intelligent robotic arm assistant. The robot arm has a set of built-in functions you can call. Given a user instruction, output a JSON plan of actions to execute and a short spoken response.

## Available Functions

### Motion
- back_zero() — Return all joints to home position [0,0,0,0,0,0]
- move_to_coords(x, y) — Move end-effector above XY at safe height (mm)
- send_angles(angles, speed) — Move all 6 joints. angles=[J1..J6] degrees, speed=1-100
- send_angle(joint_id, angle, speed) — Move one joint (1-6) to an angle
- send_coords(coords, speed) — Move to [x,y,z,rx,ry,rz]
- move_to_top_view() — Move to the overhead camera viewing position
- finger_touch(x, y) — Lower the finger to touch point (x,y) then retract
- finger_move(start_x, start_y, end_x, end_y) — Slide/push from start to end point

### Status
- get_angles() — Get current joint angles
- get_coords() — Get current TCP coordinates
- get_robot_status() — Get full robot status

### System
- power_on() — Power on the robot
- release_all_servos() — Release all servos for free manual movement
- set_led_color(r, g, b) — Set RGB LED on end-effector (0-255 each)

### Gestures
- head_shake() — Shake head (no gesture)
- head_nod() — Nod head (yes gesture)
- head_dance() — Fun dance animation

### Vision (VLM)
- vlm_move(instruction) — Use overhead camera + VLM to identify objects, then move from start object to end object. The instruction describes what to move where (e.g. "push the red block onto the star").
- vlm_vqa(question) — Take an overhead photo and answer a visual question about the workspace.
- llm_led(description) — Use LLM to convert a color description to RGB and set the LED.
- capture_image() — Take an overhead photo and save it.

### Other
- wait(seconds) — Wait for a number of seconds

## Output Format
Return ONLY a JSON object (no markdown fences) with exactly these keys:
{
  "function": ["func1(args)", "func2(args)", ...],
  "response": "A short witty response to the user (under 30 words)"
}

- "function" is a list of function call strings, in execution order
- "response" is your spoken reply to the user — be helpful and concise

## Examples

User: Go back to home position
{"function": ["back_zero()"], "response": "Heading back to home base!"}

User: First go home, then do a little dance
{"function": ["back_zero()", "head_dance()"], "response": "Let me reset first, then watch my moves!"}

User: Move to X=150, Y=-120
{"function": ["move_to_coords(150, -120)"], "response": "On my way to those coordinates."}

User: Push the red block onto the star sticker
{"function": ["vlm_move('push the red block onto the star sticker')"], "response": "I'll find the red block and push it to the star."}

User: What objects do you see on the table?
{"function": ["vlm_vqa('What objects are on the table?')"], "response": "Let me take a look at the workspace."}

User: Change LED to ocean blue
{"function": ["llm_led('ocean blue')"], "response": "Setting the LED to a beautiful ocean blue."}

User: Touch the green ball
{"function": ["vlm_touch('the green ball')"], "response": "I'll find and touch the green ball."}

User: How are you today?
{"function": [], "response": "I'm doing great! Ready to help you move things around."}
"""


class AgentPlanner:
    """
    Takes user instructions and produces an executable action plan
    using GPT-4o as the planning backbone.
    """

    def __init__(self):
        cfg = get_config().vlm
        endpoint = cfg.azure_endpoint
        parts = endpoint.split("/openai/deployments/")
        self.azure_endpoint = parts[0]
        after = parts[1] if len(parts) > 1 else ""
        self.deployment = after.split("/")[0]
        if "api-version=" in endpoint:
            self.api_version = endpoint.split("api-version=")[1].split("&")[0]
        else:
            self.api_version = "2025-01-01-preview"

        self.client = AzureOpenAI(
            azure_endpoint=self.azure_endpoint,
            api_key=cfg.azure_api_key,
            api_version=self.api_version,
        )
        self.max_tokens = cfg.max_tokens

        # Conversation history for multi-turn context
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT}
        ]

    def plan(self, user_instruction: str) -> Dict[str, Any]:
        """
        Given a user instruction, return an action plan.

        Returns:
            {"function": ["func1()", ...], "response": "..."}
        """
        self.messages.append({"role": "user", "content": user_instruction})

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=self.messages,
            max_tokens=self.max_tokens,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        logger.info(f"Agent raw plan: {raw}")

        # Parse JSON
        cleaned = raw
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        plan = json.loads(cleaned)

        # Record assistant response in conversation history
        self.messages.append({"role": "assistant", "content": raw})

        return plan

    def reset_conversation(self):
        """Clear conversation history (keep system prompt)."""
        self.messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]


# Singleton
_planner: Optional[AgentPlanner] = None


def get_planner() -> AgentPlanner:
    global _planner
    if _planner is None:
        _planner = AgentPlanner()
    return _planner
