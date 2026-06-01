"""
utils/helpers.py — Miscellaneous helper functions
"""

import re
import html
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def format_utc(dt: Optional[datetime] = None) -> str:
    """Format a UTC datetime as a human-readable string."""
    if dt is None:
        dt = utc_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return html.escape(str(text))


def sanitize_username(username: Optional[str]) -> str:
    """Return @username or 'N/A' if no username."""
    if not username:
        return "N/A"
    if not username.startswith("@"):
        return f"@{username}"
    return username


def chat_type_label(chat_type: str) -> str:
    """Friendly label for chat type."""
    mapping = {
        "channel": "Channel",
        "supergroup": "Supergroup",
        "group": "Group",
        "bot": "Bot",
        "user": "User",
    }
    return mapping.get(chat_type.lower(), chat_type.capitalize())


def truncate(text: str, max_len: int = 64) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def is_valid_keyword(keyword: str) -> bool:
    """Validate keyword: non-empty, reasonable length."""
    keyword = keyword.strip()
    if not keyword:
        return False
    if len(keyword) > 200:
        return False
    return True


def chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def format_file_size(size_bytes: int) -> str:
    """Human-friendly file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def build_search_query(keyword: str) -> str:
    """Append the monitoring emoji suffix to a keyword."""
    from config import config
    return keyword.strip() + config.SEARCH_SUFFIX
