"""
models/schemas.py — Pydantic data models matching MongoDB collections
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# Admin
# ─────────────────────────────────────────────

class AdminModel(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)
    is_active: bool = True


# ─────────────────────────────────────────────
# Session (Userbot)
# ─────────────────────────────────────────────

class SessionModel(BaseModel):
    admin_id: int
    api_id: int
    api_hash: str
    session_string: str
    phone: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)
    is_active: bool = True


# ─────────────────────────────────────────────
# Keyword
# ─────────────────────────────────────────────

class KeywordModel(BaseModel):
    admin_id: int
    keyword: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utc_now)


# ─────────────────────────────────────────────
# Search Result (inside a snapshot)
# ─────────────────────────────────────────────

class SearchResultItem(BaseModel):
    chat_id: int
    name: str
    username: Optional[str] = None
    chat_type: str  # channel | supergroup | bot
    members_count: Optional[int] = None
    photo_id: Optional[str] = None  # stored file reference


# ─────────────────────────────────────────────
# Snapshot
# ─────────────────────────────────────────────

class SnapshotModel(BaseModel):
    admin_id: int
    keyword: str
    results: List[SearchResultItem]
    captured_at: datetime = Field(default_factory=_utc_now)


# ─────────────────────────────────────────────
# Alert
# ─────────────────────────────────────────────

class AlertModel(BaseModel):
    admin_id: int
    keyword: str
    alert_type: str  # "new" | "disappeared"
    chat_id: int
    name: str
    username: Optional[str] = None
    chat_type: str
    created_at: datetime = Field(default_factory=_utc_now)
    sent: bool = False


# ─────────────────────────────────────────────
# Log Entry
# ─────────────────────────────────────────────

class LogEntry(BaseModel):
    level: str
    message: str
    created_at: datetime = Field(default_factory=_utc_now)
    meta: Dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────

class SettingsModel(BaseModel):
    admin_id: int
    monitor_interval: int = 60
    max_keywords: int = 50
    search_results_count: int = 3
    notifications_enabled: bool = True
    updated_at: datetime = Field(default_factory=_utc_now)
