"""
handlers/base.py — Admin guard decorator and shared inline keyboards
"""

from __future__ import annotations
import functools
from typing import Any, Callable, Coroutine

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from utils.logger import logger


def admin_only(func: Callable) -> Callable:
    """Decorator: restrict handler to configured admin IDs."""
    @functools.wraps(func)
    async def wrapper(event: Any, *args: Any, **kwargs: Any) -> Any:
        user_id: int = 0
        if isinstance(event, types.Message):
            user_id = event.from_user.id if event.from_user else 0
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id if event.from_user else 0
        if user_id not in config.ADMIN_IDS:
            logger.warning(f"Unauthorized access attempt by user_id={user_id}")
            if isinstance(event, types.Message):
                await event.answer("⛔ Access denied.", parse_mode=None)
            elif isinstance(event, types.CallbackQuery):
                await event.answer("⛔ Access denied.", show_alert=True)
            return
        return await func(event, *args, **kwargs)
    return wrapper


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Add Keyword",    callback_data="add_keyword"),
        InlineKeyboardButton(text="🗑 Remove Keyword", callback_data="remove_keyword"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Keywords",       callback_data="list_keywords"),
        InlineKeyboardButton(text="📊 Stats",          callback_data="show_stats"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Refresh",        callback_data="refresh_status"),
        InlineKeyboardButton(text="⚙️ Settings",       callback_data="settings_menu"),
    )
    return builder.as_markup()


def back_keyboard(callback: str = "main_menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back", callback_data=callback)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data="cancel_action")
    return builder.as_markup()


def setup_login_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 OTP Login",  callback_data="login_otp"),
        InlineKeyboardButton(text="🔲 QR Login",   callback_data="login_qr"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Cancel",     callback_data="cancel_setup"),
    )
    return builder.as_markup()


def confirm_keyboard(yes_cb: str, no_cb: str = "cancel_action") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Yes", callback_data=yes_cb),
        InlineKeyboardButton(text="❌ No",  callback_data=no_cb),
    )
    return builder.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏱ Change Interval",      callback_data="set_interval"),
        InlineKeyboardButton(text="🔔 Toggle Notifications", callback_data="toggle_notifications"),
    )
    builder.row(
        InlineKeyboardButton(text="🔌 Disconnect Userbot", callback_data="disconnect_userbot"),
        InlineKeyboardButton(text="⬅️ Back",               callback_data="main_menu"),
    )
    return builder.as_markup()
