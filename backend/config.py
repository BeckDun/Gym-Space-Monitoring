import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./gsm.db")
USE_MOCK_MLLM: bool = os.environ.get("USE_MOCK_MLLM", "0") == "1" or not GEMINI_API_KEY

ZONE_THRESHOLDS: dict[str, int] = {
    "cardio_zone": 5,
    "smart_machine_zone": 5,
    "cycling_zone": 5,
    "functional_zone": 5,
    "entrance": 10,
}

FALL_CONFIDENCE_THRESHOLD: float = 6.0
CONFLICT_CONFIDENCE_THRESHOLD: float = 6.0
MLLM_MODEL: str = "gemini-2.5-flash"
