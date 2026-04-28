import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/gsm")

ZONE_THRESHOLDS: dict[str, int] = {
    "zone_a": 30,
    "zone_b": 25,
    "zone_c": 20,
    "zone_d": 20,
    "entrance": 10,
}

FALL_CONFIDENCE_THRESHOLD: float = 6.0
CONFLICT_CONFIDENCE_THRESHOLD: float = 6.0
MLLM_MODEL: str = "gemini-2.0-flash"
