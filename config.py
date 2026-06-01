"""
config.py — Central configuration loader
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _parse_int_list(raw: str) -> List[int]:
    """Parse comma-separated integers."""
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            result.append(int(part))
    return result


class Config:
    # Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # Admins
    ADMIN_IDS: List[int] = _parse_int_list(os.getenv("ADMIN_IDS", ""))

    # MongoDB
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "tgmonitor")

    # Monitor
    MONITOR_INTERVAL: int = int(os.getenv("MONITOR_INTERVAL", "60"))
    MAX_KEYWORDS: int = int(os.getenv("MAX_KEYWORDS", "50"))
    SEARCH_RESULTS_COUNT: int = int(os.getenv("SEARCH_RESULTS_COUNT", "3"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Search emoji suffix appended to every query
    SEARCH_SUFFIX: str = " %@%@%@@%@%"

    # Custom emoji IDs
    EMOJI_IDS = {
        "✔️": 5206607081334906820,
        "🔎": 5429419796988970289,
        "💙": 5382073967303485282,
        "👌": 5382026293166489702,
        "🌸": 5467894367429607924,
        "🔜": 5920285072308572176,
        "☑️": 5303305267822222510,
        "🟣": 5228788444230071758,
        "⏳": 5307773751796964107,
        "😀": 6134191632108489706,
        "💔": 5273842895978251304,
    }

    @classmethod
    def validate(cls) -> None:
        """Validate required config values."""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required in .env")
        if not cls.ADMIN_IDS:
            raise ValueError("ADMIN_IDS is required in .env")


config = Config()
