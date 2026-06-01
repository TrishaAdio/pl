"""
services/monitor.py — Core monitoring service
Compares snapshots and fires alerts on changes.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from database import db
from services.userbot import userbot_manager
from utils.logger import logger
from utils.helpers import build_search_query, utc_now


class MonitorService:
    """Runs keyword searches and detects new/disappeared results."""

    def __init__(self) -> None:
        self._running = False

    async def run_once(self) -> None:
        """Run one full monitoring cycle across all admins/keywords."""
        keywords = await db.get_all_enabled_keywords()
        if not keywords:
            return

        logger.search(f"Monitor cycle: {len(keywords)} keyword(s)")

        for kw_doc in keywords:
            admin_id = kw_doc["admin_id"]
            keyword = kw_doc["keyword"]

            session = userbot_manager.get_session(admin_id)
            if not session or not session.is_connected:
                continue

            query = build_search_query(keyword)
            results = await session.search_globally(query, limit=3)

            if results is None:
                results = []

            await self._process_results(admin_id, keyword, results)
            await asyncio.sleep(2)  # throttle between keywords

    async def _process_results(
        self,
        admin_id: int,
        keyword: str,
        new_results: List[Dict[str, Any]],
    ) -> None:
        """Compare new results with previous snapshot and emit alerts."""
        prev_snap = await db.get_latest_snapshot(admin_id, keyword)

        new_ids: Set[int] = {r["chat_id"] for r in new_results}
        old_ids: Set[int] = set()
        old_map: Dict[int, Dict] = {}

        if prev_snap:
            for r in prev_snap.get("results", []):
                cid = r["chat_id"]
                old_ids.add(cid)
                old_map[cid] = r

        # Appeared
        appeared = [r for r in new_results if r["chat_id"] not in old_ids]
        # Disappeared
        disappeared_ids = old_ids - new_ids
        disappeared = [old_map[cid] for cid in disappeared_ids]

        # Save snapshot
        await db.save_snapshot(admin_id, keyword, new_results)

        # Emit alerts
        for item in appeared:
            logger.alert(f"NEW: '{item['name']}' for keyword='{keyword}' admin={admin_id}")
            await self._emit_new_alert(admin_id, keyword, item)

        for item in disappeared:
            logger.alert(f"GONE: '{item['name']}' for keyword='{keyword}' admin={admin_id}")
            await self._emit_disappeared_alert(admin_id, keyword, item)

    async def _emit_new_alert(
        self, admin_id: int, keyword: str, item: Dict[str, Any]
    ) -> None:
        await db.save_alert(
            admin_id=admin_id,
            keyword=keyword,
            alert_type="new",
            chat_id=item["chat_id"],
            name=item["name"],
            username=item.get("username"),
            chat_type=item.get("chat_type", "channel"),
        )
        await db.write_log(
            "ALERT",
            f"New result: {item['name']} for keyword '{keyword}'",
            {"admin_id": admin_id, "chat_id": item["chat_id"]},
        )
        # Notify via bot
        await self._send_new_notification(admin_id, keyword, item)

    async def _emit_disappeared_alert(
        self, admin_id: int, keyword: str, item: Dict[str, Any]
    ) -> None:
        await db.save_alert(
            admin_id=admin_id,
            keyword=keyword,
            alert_type="disappeared",
            chat_id=item["chat_id"],
            name=item["name"],
            username=item.get("username"),
            chat_type=item.get("chat_type", "channel"),
        )
        await db.write_log(
            "ALERT",
            f"Disappeared: {item['name']} for keyword '{keyword}'",
            {"admin_id": admin_id, "chat_id": item["chat_id"]},
        )
        await self._send_disappeared_notification(admin_id, keyword, item)

    async def _send_new_notification(
        self, admin_id: int, keyword: str, item: Dict[str, Any]
    ) -> None:
        """Download photo, generate card, send via bot."""
        from services.image_gen import generate_profile_card
        try:
            session = userbot_manager.get_session(admin_id)
            photo_bytes = None
            if session:
                photo_bytes = await session.download_profile_photo(item["chat_id"])

            card_bytes = generate_profile_card(
                name=item["name"],
                username=item.get("username"),
                chat_id=item["chat_id"],
                keyword=keyword,
                chat_type=item.get("chat_type", "channel"),
                detected_at=utc_now(),
                photo_bytes=photo_bytes,
                alert_type="new",
            )

            from services.notifier import notifier
            await notifier.send_new_alert(admin_id, keyword, item, card_bytes)
        except Exception as exc:
            logger.error(f"Failed to send new notification: {exc}")

    async def _send_disappeared_notification(
        self, admin_id: int, keyword: str, item: Dict[str, Any]
    ) -> None:
        try:
            from services.notifier import notifier
            await notifier.send_disappeared_alert(admin_id, keyword, item)
        except Exception as exc:
            logger.error(f"Failed to send disappeared notification: {exc}")


monitor_service = MonitorService()
