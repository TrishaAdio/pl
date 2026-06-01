"""
services/userbot.py — Telethon userbot manager
Handles: session creation, OTP login, QR login, global search
"""

from __future__ import annotations
import asyncio
import io
import os
import time
import base64
from typing import Any, Callable, Dict, List, Optional, Tuple

import qrcode
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.auth import ExportLoginTokenRequest, ImportLoginTokenRequest
from telethon.tl.types import (
    Channel,
    Chat,
    User,
    ChannelForbidden,
    ChatForbidden,
    InputPeerEmpty,
)
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    FloodWaitError,
    AuthTokenAlreadyAcceptedError,
    AuthTokenExpiredError,
)

from config import config
from utils.logger import logger


class UserBotSession:
    """Manages a single Telethon session for one admin."""

    def __init__(self, admin_id: int, api_id: int, api_hash: str, session_string: str = "") -> None:
        self.admin_id = admin_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.client: Optional[TelegramClient] = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Telegram using stored session string."""
        try:
            self.client = TelegramClient(
                StringSession(self.session_string),
                self.api_id,
                self.api_hash,
                device_model="TGMonitor Bot",
                system_version="Ubuntu 24.04",
                app_version="1.0.0",
            )
            await self.client.connect()
            if await self.client.is_user_authorized():
                self._connected = True
                me = await self.client.get_me()
                logger.userbot(f"Session active: {me.first_name} (@{me.username}) — admin_id={self.admin_id}")
                return True
            else:
                logger.warning(f"Session not authorized for admin_id={self.admin_id}")
                return False
        except Exception as exc:
            logger.error(f"Failed to connect userbot for admin_id={self.admin_id}: {exc}")
            return False

    async def disconnect(self) -> None:
        if self.client and self._connected:
            await self.client.disconnect()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.client is not None

    def get_session_string(self) -> str:
        if self.client:
            return self.client.session.save()
        return ""

    async def search_globally(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Search Telegram globally using SearchRequest and return
        up to `limit` channels/supergroups/bots.
        """
        if not self.is_connected:
            logger.error(f"Userbot not connected for admin_id={self.admin_id}")
            return []
        try:
            logger.search(f"Searching: '{query}' (admin_id={self.admin_id})")
            result = await self.client(SearchRequest(q=query, limit=50))
            found = []
            for chat in result.chats:
                if len(found) >= limit:
                    break
                if isinstance(chat, (ChannelForbidden, ChatForbidden)):
                    continue
                if isinstance(chat, Channel):
                    chat_type = "channel" if chat.broadcast else "supergroup"
                    found.append({
                        "chat_id": int(f"-100{chat.id}"),
                        "name": chat.title or "Unknown",
                        "username": chat.username,
                        "chat_type": chat_type,
                        "members_count": getattr(chat, "participants_count", None),
                    })
                elif isinstance(chat, Chat):
                    found.append({
                        "chat_id": -chat.id,
                        "name": chat.title or "Unknown",
                        "username": None,
                        "chat_type": "group",
                        "members_count": getattr(chat, "participants_count", None),
                    })
            # Also scan users for bots
            for user in getattr(result, "users", []):
                if len(found) >= limit:
                    break
                if isinstance(user, User) and user.bot:
                    found.append({
                        "chat_id": user.id,
                        "name": (user.first_name or "") + (" " + user.last_name if user.last_name else ""),
                        "username": user.username,
                        "chat_type": "bot",
                        "members_count": None,
                    })
            logger.search(f"Found {len(found)} results for '{query}'")
            return found[:limit]
        except FloodWaitError as e:
            logger.warning(f"FloodWait {e.seconds}s for search '{query}'")
            await asyncio.sleep(e.seconds)
            return []
        except Exception as exc:
            logger.error(f"Search error for '{query}': {exc}")
            return []

    async def download_profile_photo(self, chat_id: int) -> Optional[bytes]:
        """Download and return profile photo bytes, or None."""
        if not self.is_connected:
            return None
        try:
            entity = await self.client.get_entity(chat_id)
            buf = io.BytesIO()
            result = await self.client.download_profile_photo(entity, file=buf)
            if result:
                return buf.getvalue()
            return None
        except Exception as exc:
            logger.warning(f"Could not download photo for {chat_id}: {exc}")
            return None


class OTPLoginFlow:
    """
    Handles phone-based OTP login flow for a given admin.
    The admin sends messages through the bot; state is tracked here.
    """

    def __init__(self, admin_id: int, api_id: int, api_hash: str) -> None:
        self.admin_id = admin_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.client: Optional[TelegramClient] = None
        self.phone: Optional[str] = None
        self.phone_code_hash: Optional[str] = None
        self.step: str = "phone"  # phone → code → password (if 2FA) → done

    async def start(self) -> None:
        """Create client and connect (no auth yet)."""
        self.client = TelegramClient(
            StringSession(),
            self.api_id,
            self.api_hash,
            device_model="TGMonitor Bot",
            system_version="Ubuntu 24.04",
            app_version="1.0.0",
        )
        await self.client.connect()

    async def send_code(self, phone: str) -> str:
        """Send verification code. Returns instructions."""
        self.phone = phone
        try:
            result = await self.client.send_code_request(phone)
            self.phone_code_hash = result.phone_code_hash
            self.step = "code"
            return f"Code sent to {phone}. Please enter the verification code."
        except Exception as exc:
            return f"Error sending code: {exc}"

    async def submit_code(self, code: str) -> Tuple[bool, str, Optional[str]]:
        """
        Submit the OTP code.
        Returns: (success, message, session_string_or_None)
        """
        try:
            await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
            session_str = self.client.session.save()
            self.step = "done"
            return True, "Logged in successfully!", session_str
        except SessionPasswordNeededError:
            self.step = "password"
            return False, "2FA password required. Please enter your Telegram password.", None
        except PhoneCodeInvalidError:
            return False, "Invalid code. Please try again.", None
        except Exception as exc:
            return False, f"Login error: {exc}", None

    async def submit_password(self, password: str) -> Tuple[bool, str, Optional[str]]:
        """
        Submit 2FA password.
        Returns: (success, message, session_string_or_None)
        """
        try:
            await self.client.sign_in(password=password)
            session_str = self.client.session.save()
            self.step = "done"
            return True, "Logged in with 2FA!", session_str
        except PasswordHashInvalidError:
            return False, "Wrong password. Please try again.", None
        except Exception as exc:
            return False, f"2FA error: {exc}", None

    async def cleanup(self) -> None:
        if self.client:
            await self.client.disconnect()


class QRLoginFlow:
    """
    Handles QR code login flow.
    Generates a QR code image and polls for authorization.
    """

    def __init__(self, admin_id: int, api_id: int, api_hash: str) -> None:
        self.admin_id = admin_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.client: Optional[TelegramClient] = None
        self._authorized = False
        self._session_string: Optional[str] = None
        self._cancel = False

    async def start(self) -> None:
        self.client = TelegramClient(
            StringSession(),
            self.api_id,
            self.api_hash,
            device_model="TGMonitor Bot",
            system_version="Ubuntu 24.04",
            app_version="1.0.0",
        )
        await self.client.connect()

    async def generate_qr_image(self) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Request a QR login token and return (png_bytes, error_message).
        """
        try:
            result = await self.client(
                ExportLoginTokenRequest(
                    api_id=self.api_id,
                    api_hash=self.api_hash,
                    except_ids=[],
                )
            )
            # Build the tg://login?token=... URL
            token_b64 = base64.urlsafe_b64encode(result.token).decode()
            qr_url = f"tg://login?token={token_b64}"
            # Generate QR PNG
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue(), None
        except Exception as exc:
            logger.error(f"QR generation error: {exc}")
            return None, str(exc)

    async def wait_for_auth(self, timeout: int = 120) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Poll Telegram until the QR is scanned or timeout.
        Returns: (authorized, session_string, error)
        """
        deadline = time.time() + timeout
        while time.time() < deadline and not self._cancel:
            try:
                if await self.client.is_user_authorized():
                    session_str = self.client.session.save()
                    self._authorized = True
                    self._session_string = session_str
                    logger.userbot(f"QR login authorized for admin_id={self.admin_id}")
                    return True, session_str, None
            except Exception:
                pass
            await asyncio.sleep(3)
        if self._cancel:
            return False, None, "Login cancelled."
        return False, None, "QR code timed out. Please try again."

    def cancel(self) -> None:
        self._cancel = True

    async def cleanup(self) -> None:
        if self.client:
            await self.client.disconnect()


class UserBotManager:
    """
    Global manager holding active UserBotSession instances,
    keyed by admin_id.
    """

    def __init__(self) -> None:
        self._sessions: Dict[int, UserBotSession] = {}

    async def load_from_db(self) -> None:
        """Load all active sessions from MongoDB and connect them."""
        from database import db
        sessions = await db.get_all_active_sessions()
        for sess in sessions:
            admin_id = sess["admin_id"]
            ubs = UserBotSession(
                admin_id=admin_id,
                api_id=sess["api_id"],
                api_hash=sess["api_hash"],
                session_string=sess["session_string"],
            )
            ok = await ubs.connect()
            if ok:
                self._sessions[admin_id] = ubs
                logger.userbot(f"Session loaded for admin_id={admin_id}")
            else:
                logger.warning(f"Could not reconnect session for admin_id={admin_id}")

    async def add_session(
        self,
        admin_id: int,
        api_id: int,
        api_hash: str,
        session_string: str,
        phone: Optional[str] = None,
    ) -> bool:
        """Save session to DB and activate it."""
        from database import db
        await db.save_session(admin_id, api_id, api_hash, session_string, phone)
        ubs = UserBotSession(
            admin_id=admin_id,
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
        )
        ok = await ubs.connect()
        if ok:
            # Disconnect existing if any
            if admin_id in self._sessions:
                await self._sessions[admin_id].disconnect()
            self._sessions[admin_id] = ubs
            logger.userbot(f"New session activated for admin_id={admin_id}")
        return ok

    def get_session(self, admin_id: int) -> Optional[UserBotSession]:
        return self._sessions.get(admin_id)

    def has_session(self, admin_id: int) -> bool:
        sess = self._sessions.get(admin_id)
        return sess is not None and sess.is_connected

    async def remove_session(self, admin_id: int) -> None:
        if admin_id in self._sessions:
            await self._sessions[admin_id].disconnect()
            del self._sessions[admin_id]
        from database import db
        await db.delete_session(admin_id)

    async def shutdown(self) -> None:
        for ubs in self._sessions.values():
            await ubs.disconnect()
        self._sessions.clear()


# Singleton
userbot_manager = UserBotManager()
