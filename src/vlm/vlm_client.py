"""
VLM (Vision-Language Model) client for Azure OpenAI GPT-4o.

Provides two main capabilities:
  1. Object grounding  — detect start/end objects and return bounding boxes
  2. Visual QA         — answer questions about what the camera sees
"""

import os
import json
import base64
import logging
from typing import Dict, Any, Optional

from openai import AzureOpenAI

from src.cobot.config import get_config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# System prompts
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_GROUNDING = """You are a vision system for a robotic arm. Given an overhead camera image of a workspace and a natural language instruction, you must:

1. Identify the START object (the object to be moved/touched) and the END object (the target/destination).
2. Find the bounding box of each object in the image.
3. Return your answer as a JSON object with EXACTLY this structure:

{
  "start": "<name of start object>",
  "start_xyxy": [[x1, y1], [x2, y2]],
  "end": "<name of end object>",
  "end_xyxy": [[x1, y1], [x2, y2]]
}

Where [x1,y1] is the top-left corner and [x2,y2] is the bottom-right corner.
Coordinates are normalized to a 0-999 scale (0=left/top edge, 999=right/bottom edge).

IMPORTANT:
- Return ONLY the JSON object, no markdown, no explanation, no code fences.
- Be as precise as possible with the bounding boxes.

The instruction is:
"""

SYSTEM_PROMPT_SINGLE_OBJECT = """You are a vision system for a robotic arm. Given an overhead camera image of a workspace and a natural language description of ONE object, you must:

1. Find the described object in the image.
2. Return a JSON object with EXACTLY this structure:

{
  "object": "<name of object>",
  "xyxy": [[x1, y1], [x2, y2]]
}

Where [x1,y1] is the top-left and [x2,y2] is the bottom-right corner.
Coordinates are normalized to a 0-999 scale.

Return ONLY the JSON. The object to find is:
"""

SYSTEM_PROMPT_VQA = """You are a vision assistant for a robotic arm with an overhead camera. Describe what you see in the image clearly and concisely. Answer the user's question based on the image content.

The question is:
"""


class VLMClient:
    """
    Calls Azure OpenAI GPT-4o with vision to perform grounding and VQA.
    """

    def __init__(self):
        cfg = get_config().vlm
        # Parse the full Azure endpoint URL to extract base and deployment
        # Expected format: https://<resource>.cognitiveservices.azure.com/openai/deployments/<deployment>/chat/completions?api-version=<ver>
        endpoint = cfg.azure_endpoint
        self.api_key = cfg.azure_api_key
        self.max_tokens = cfg.max_tokens

        # Extract base URL and api-version from the full endpoint
        # e.g. https://bugtotest-resource.cognitiveservices.azure.com
        parts = endpoint.split("/openai/deployments/")
        self.azure_endpoint = parts[0]

        # Extract deployment name
        after = parts[1] if len(parts) > 1 else ""
        self.deployment = after.split("/")[0]

        # Extract api-version
        if "api-version=" in endpoint:
            self.api_version = endpoint.split("api-version=")[1].split("&")[0]
        else:
            self.api_version = "2025-01-01-preview"

        self.client = AzureOpenAI(
            azure_endpoint=self.azure_endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )

    def _encode_image(self, image_path: str) -> str:
        """Read an image file and return base64-encoded string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _call_vision(self, system_prompt: str, user_text: str, image_path: str) -> str:
        """Send an image + text prompt to GPT-4o and return the raw text response."""
        image_b64 = self._encode_image(image_path)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system_prompt + user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                        },
                    },
                ],
            }
        ]

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _call_text(self, system_prompt: str, user_text: str) -> str:
        """Send a text-only prompt to GPT-4o."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

    # ── Public API ───────────────────────────────────────────────────────

    def ground_objects(self, instruction: str, image_path: str) -> Dict[str, Any]:
        """
        Given a natural language instruction (e.g. "put the red block on the star"),
        detect the start and end objects and return bounding boxes.

        Returns dict with keys: start, start_xyxy, end, end_xyxy
        """
        raw = self._call_vision(SYSTEM_PROMPT_GROUNDING, instruction, image_path)
        logger.info(f"VLM grounding raw response: {raw}")

        # Try to parse JSON — handle potential markdown code fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove code fences
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        result = json.loads(cleaned)
        return result

    def detect_single_object(self, description: str, image_path: str) -> Dict[str, Any]:
        """
        Find a single described object in the image.

        Returns dict with keys: object, xyxy
        """
        raw = self._call_vision(SYSTEM_PROMPT_SINGLE_OBJECT, description, image_path)
        logger.info(f"VLM single-object raw response: {raw}")

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        return json.loads(cleaned)

    def visual_qa(self, question: str, image_path: str) -> str:
        """
        Ask a question about the overhead camera image.

        Returns the VLM's text answer.
        """
        answer = self._call_vision(SYSTEM_PROMPT_VQA, question, image_path)
        logger.info(f"VLM VQA answer: {answer}")
        return answer

    def determine_led_color(self, description: str) -> tuple:
        """
        Ask GPT-4o to convert a color description to an RGB tuple.
        e.g. "the color of Lake Baikal" → (30, 100, 200)
        """
        prompt = (
            "Convert the following color description to an RGB tuple (0-255). "
            "Return ONLY the tuple, e.g. (255, 30, 60). No other text.\n\n"
        )
        raw = self._call_text(prompt, description)
        # Parse the tuple
        return eval(raw.strip())


# Singleton
_vlm_client: Optional[VLMClient] = None


def get_vlm_client() -> VLMClient:
    global _vlm_client
    if _vlm_client is None:
        _vlm_client = VLMClient()
    return _vlm_client
