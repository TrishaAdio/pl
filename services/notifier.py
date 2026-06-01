"""
services/notifier.py — Sends formatted alert messages to admins via aiogram bot.
"""

from __future__ import annotations
import io
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from aiogram import Bot
from aiogram.types import BufferedInputFile

from utils.helpers import sanitize_username, chat_type_label, format_utc, utc_now
from utils.logger import logger


class NotifierService:
    """Sends new/disappeared alerts via the aiogram bot."""

    def __init__(self) -> None:
        self._bot: Optional[Bot] = None

    def set_bot(self, bot: Bot) -> None:
        self._bot = bot

    async def send_new_alert(
        self,
        admin_id: int,
        keyword: str,
        item: Dict[str, Any],
        card_bytes: bytes,
    ) -> None:
        if not self._bot:
            logger.error("Notifier: bot not set")
            return

        uname = sanitize_username(item.get("username"))
        ctype = chat_type_label(item.get("chat_type", "channel"))
        ts = format_utc(utc_now())

        caption = (
            f"<b>✔️🔎💙👌🌸 New Discovery</b>\n"
            f"<blockquote>"
            f"Keyword  : <code>{keyword}</code>\n"
            f"Name     : <b>{item['name']}</b>\n"
            f"Username : {uname}\n"
            f"Chat ID  : <code>{item['chat_id']}</code>\n"
            f"Type     : {ctype}\n"
            f"Detected : {ts}"
            f"</blockquote>"
        )

        try:
            photo_file = BufferedInputFile(card_bytes, filename="profile_card.png")
            await self._bot.send_photo(
                chat_id=admin_id,
                photo=photo_file,
                caption=caption,
                parse_mode="HTML",
            )
            logger.success(f"New alert sent to admin_id={admin_id}: {item['name']}")
        except Exception as exc:
            logger.error(f"Failed to send new alert to {admin_id}: {exc}")
            # Fallback text only
            try:
                await self._bot.send_message(
                    chat_id=admin_id,
                    text=caption,
                    parse_mode="HTML",
                )
            except Exception as exc2:
                logger.error(f"Fallback text also failed: {exc2}")

    async def send_disappeared_alert(
        self,
        admin_id: int,
        keyword: str,
        item: Dict[str, Any],
    ) -> None:
        if not self._bot:
            return

        uname = sanitize_username(item.get("username"))
        ts = format_utc(utc_now())

        text = (
            f"<b>💔 Oh Sad...</b>\n"
            f"<blockquote>"
            f"{item['name']}\n"
            f"Username : {uname}\n"
            f"Chat ID  : <code>{item['chat_id']}</code>\n"
            f"Can't find this anymore. Maybe it's gone?\n"
            f"Date     : {ts}"
            f"</blockquote>"
        )

        try:
            await self._bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML",
            )
            logger.success(f"Disappeared alert sent to admin_id={admin_id}: {item['name']}")
        except Exception as exc:
            logger.error(f"Failed to send disappeared alert to {admin_id}: {exc}")

    async def send_message(self, admin_id: int, text: str, parse_mode: str = "HTML") -> None:
        """Generic message sender."""
        if not self._bot:
            return
        try:
            await self._bot.send_message(chat_id=admin_id, text=text, parse_mode=parse_mode)
        except Exception as exc:
            logger.error(f"send_message failed to {admin_id}: {exc}")


notifier = NotifierService()
