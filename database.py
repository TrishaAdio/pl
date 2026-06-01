"""
database.py — Motor async MongoDB client with full CRUD for all collections
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import motor.motor_asyncio
from pymongo import ASCENDING, DESCENDING

from config import config
from utils.logger import logger
from models.schemas import (
    AdminModel,
    SessionModel,
    KeywordModel,
    SnapshotModel,
    SearchResultItem,
    AlertModel,
    LogEntry,
    SettingsModel,
)


class Database:
    """Async MongoDB wrapper using Motor."""

    def __init__(self) -> None:
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None

    async def connect(self) -> None:
        """Connect to MongoDB and ensure indexes."""
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            config.MONGO_URI,
            serverSelectionTimeoutMS=5000,
        )
        self.db = self.client[config.MONGO_DB]
        await self._ping()
        await self._ensure_indexes()
        logger.database(f"Connected to MongoDB: {config.MONGO_URI}/{config.MONGO_DB}")

    async def _ping(self) -> None:
        await self.client.admin.command("ping")

    async def disconnect(self) -> None:
        if self.client:
            self.client.close()
            logger.database("MongoDB connection closed.")

    async def _ensure_indexes(self) -> None:
        """Create indexes for all collections."""
        db = self.db
        # admins
        await db.admins.create_index("user_id", unique=True)
        # sessions
        await db.sessions.create_index("admin_id", unique=True)
        # keywords
        await db.keywords.create_index([("admin_id", ASCENDING), ("keyword", ASCENDING)], unique=True)
        # snapshots
        await db.snapshots.create_index([("admin_id", ASCENDING), ("keyword", ASCENDING)])
        await db.snapshots.create_index("captured_at", expireAfterSeconds=86400 * 30)  # 30d TTL
        # alerts
        await db.alerts.create_index([("admin_id", ASCENDING), ("created_at", DESCENDING)])
        # logs
        await db.logs.create_index("created_at", expireAfterSeconds=86400 * 7)  # 7d TTL
        # settings
        await db.settings.create_index("admin_id", unique=True)
        logger.database("Indexes verified.")

    # ─────────────────────────────────────────
    # Admins
    # ─────────────────────────────────────────

    async def upsert_admin(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> None:
        await self.db.admins.update_one(
            {"user_id": user_id},
            {"$set": {"username": username, "first_name": first_name, "is_active": True},
             "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    async def get_admin(self, user_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.admins.find_one({"user_id": user_id})

    async def get_all_admins(self) -> List[Dict[str, Any]]:
        cursor = self.db.admins.find({"is_active": True})
        return await cursor.to_list(length=1000)

    # ─────────────────────────────────────────
    # Sessions
    # ─────────────────────────────────────────

    async def save_session(
        self,
        admin_id: int,
        api_id: int,
        api_hash: str,
        session_string: str,
        phone: Optional[str] = None,
    ) -> None:
        await self.db.sessions.update_one(
            {"admin_id": admin_id},
            {
                "$set": {
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "session_string": session_string,
                    "phone": phone,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        logger.database(f"Session saved for admin_id={admin_id}")

    async def get_session(self, admin_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.sessions.find_one({"admin_id": admin_id, "is_active": True})

    async def delete_session(self, admin_id: int) -> None:
        await self.db.sessions.update_one(
            {"admin_id": admin_id},
            {"$set": {"is_active": False}},
        )

    async def get_all_active_sessions(self) -> List[Dict[str, Any]]:
        cursor = self.db.sessions.find({"is_active": True})
        return await cursor.to_list(length=100)

    # ─────────────────────────────────────────
    # Keywords
    # ─────────────────────────────────────────

    async def add_keyword(self, admin_id: int, keyword: str) -> bool:
        """Returns True if added, False if already exists."""
        existing = await self.db.keywords.find_one({"admin_id": admin_id, "keyword": keyword})
        if existing:
            return False
        count = await self.db.keywords.count_documents({"admin_id": admin_id, "enabled": True})
        if count >= config.MAX_KEYWORDS:
            raise ValueError(f"Maximum keyword limit ({config.MAX_KEYWORDS}) reached.")
        await self.db.keywords.insert_one(
            KeywordModel(admin_id=admin_id, keyword=keyword).model_dump()
        )
        logger.database(f"Keyword added: '{keyword}' for admin_id={admin_id}")
        return True

    async def delete_keyword(self, admin_id: int, keyword: str) -> bool:
        """Returns True if deleted."""
        result = await self.db.keywords.delete_one({"admin_id": admin_id, "keyword": keyword})
        if result.deleted_count:
            logger.database(f"Keyword deleted: '{keyword}' for admin_id={admin_id}")
            # Remove associated snapshots
            await self.db.snapshots.delete_many({"admin_id": admin_id, "keyword": keyword})
            return True
        return False

    async def get_keywords(self, admin_id: int) -> List[Dict[str, Any]]:
        cursor = self.db.keywords.find({"admin_id": admin_id, "enabled": True})
        return await cursor.to_list(length=1000)

    async def get_all_enabled_keywords(self) -> List[Dict[str, Any]]:
        cursor = self.db.keywords.find({"enabled": True})
        return await cursor.to_list(length=10000)

    # ─────────────────────────────────────────
    # Snapshots
    # ─────────────────────────────────────────

    async def save_snapshot(
        self,
        admin_id: int,
        keyword: str,
        results: List[Dict[str, Any]],
    ) -> None:
        items = [SearchResultItem(**r) for r in results]
        snapshot = SnapshotModel(
            admin_id=admin_id,
            keyword=keyword,
            results=items,
        )
        await self.db.snapshots.insert_one(snapshot.model_dump())

    async def get_latest_snapshot(self, admin_id: int, keyword: str) -> Optional[Dict[str, Any]]:
        return await self.db.snapshots.find_one(
            {"admin_id": admin_id, "keyword": keyword},
            sort=[("captured_at", DESCENDING)],
        )

    async def get_previous_snapshot(self, admin_id: int, keyword: str) -> Optional[Dict[str, Any]]:
        """Return the second-to-last snapshot (for comparison)."""
        cursor = self.db.snapshots.find(
            {"admin_id": admin_id, "keyword": keyword},
            sort=[("captured_at", DESCENDING)],
        ).skip(1).limit(1)
        docs = await cursor.to_list(length=1)
        return docs[0] if docs else None

    async def count_snapshots(self, admin_id: int) -> int:
        return await self.db.snapshots.count_documents({"admin_id": admin_id})

    # ─────────────────────────────────────────
    # Alerts
    # ─────────────────────────────────────────

    async def save_alert(
        self,
        admin_id: int,
        keyword: str,
        alert_type: str,
        chat_id: int,
        name: str,
        username: Optional[str],
        chat_type: str,
    ) -> str:
        alert = AlertModel(
            admin_id=admin_id,
            keyword=keyword,
            alert_type=alert_type,
            chat_id=chat_id,
            name=name,
            username=username,
            chat_type=chat_type,
        )
        result = await self.db.alerts.insert_one(alert.model_dump())
        return str(result.inserted_id)

    async def mark_alert_sent(self, alert_id: str) -> None:
        from bson import ObjectId
        await self.db.alerts.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {"sent": True}},
        )

    async def get_recent_alerts(self, admin_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        cursor = self.db.alerts.find(
            {"admin_id": admin_id},
            sort=[("created_at", DESCENDING)],
        ).limit(limit)
        return await cursor.to_list(length=limit)

    async def count_alerts(self, admin_id: int) -> int:
        return await self.db.alerts.count_documents({"admin_id": admin_id})

    # ─────────────────────────────────────────
    # Logs
    # ─────────────────────────────────────────

    async def write_log(self, level: str, message: str, meta: Optional[Dict] = None) -> None:
        entry = LogEntry(level=level, message=message, meta=meta or {})
        await self.db.logs.insert_one(entry.model_dump())

    async def get_recent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        cursor = self.db.logs.find(
            {},
            sort=[("created_at", DESCENDING)],
        ).limit(limit)
        return await cursor.to_list(length=limit)

    # ─────────────────────────────────────────
    # Settings
    # ─────────────────────────────────────────

    async def get_settings(self, admin_id: int) -> Dict[str, Any]:
        doc = await self.db.settings.find_one({"admin_id": admin_id})
        if not doc:
            # Create defaults
            default = SettingsModel(admin_id=admin_id)
            await self.db.settings.insert_one(default.model_dump())
            return default.model_dump()
        return doc

    async def update_settings(self, admin_id: int, **kwargs: Any) -> None:
        kwargs["updated_at"] = datetime.now(timezone.utc)
        await self.db.settings.update_one(
            {"admin_id": admin_id},
            {"$set": kwargs},
            upsert=True,
        )

    # ─────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────

    async def get_stats(self, admin_id: int) -> Dict[str, Any]:
        keyword_count = await self.db.keywords.count_documents({"admin_id": admin_id, "enabled": True})
        alert_count = await self.count_alerts(admin_id)
        snapshot_count = await self.count_snapshots(admin_id)
        session = await self.get_session(admin_id)
        return {
            "keywords": keyword_count,
            "alerts": alert_count,
            "snapshots": snapshot_count,
            "has_session": session is not None,
            "session_phone": session.get("phone") if session else None,
        }


# Singleton instance
db = Database()
