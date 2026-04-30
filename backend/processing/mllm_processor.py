from __future__ import annotations

import logging

from google import genai
from google.genai import types

from backend.config import GEMINI_API_KEY, MLLM_MODEL, USE_MOCK_MLLM
from backend.sensor.sensor_interface import Event

logger = logging.getLogger(__name__)


class MLLMProcessor:
    """
    Integration with the external Gemini MLLM.
    Receives video Events from the Sensor Interface and returns structured text.

    Mirrors gemini_example.py exactly:
        video_bytes = open(video_file_name, 'rb').read()
        response = client.models.generate_content(
            model='gemini-...',
            contents=types.Content(parts=[
                types.Part(inline_data=types.Blob(data=video_bytes, mime_type='video/mp4')),
                types.Part(text=prompt)
            ])
        )
    """

    def __init__(self) -> None:
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def analyze(self, event: Event, prompt: str) -> str:
        """
        Send a video event to Gemini with the given prompt.
        Returns the raw response text for the calling detector to parse.
        Only for videos < 20 MB (inline_data path).
        """
        if event.type != "video":
            raise ValueError(f"MLLMProcessor expects a 'video' event, got: {event.type!r}")

        video_bytes: bytes = event.payload["video_bytes"]
        mime_type: str = event.payload.get("mime_type", "video/mp4")

        logger.info(
            "Sending %.1f MB video to Gemini (zone=%s)",
            len(video_bytes) / 1_048_576,
            event.zone_id,
        )

        if USE_MOCK_MLLM:
            logger.info("[MOCK] Returning simulated MLLM response for zone=%s", event.zone_id)
            if "fall" in prompt.lower():
                result = "Fall: 8, Confidence: 9"
            else:
                result = "Conflict: 7, Confidence: 8"
            return result

        response = self.client.models.generate_content(
            model=MLLM_MODEL,
            contents=types.Content(
                parts=[
                    types.Part(inline_data=types.Blob(data=video_bytes, mime_type=mime_type)),
                    types.Part(text=prompt),
                ]
            ),
        )

        result = response.text
        logger.info("Gemini response (zone=%s): %s", event.zone_id, result)
        return result
