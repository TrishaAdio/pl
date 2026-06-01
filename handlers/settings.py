"""
handlers/settings.py — Settings menu, interval change, notifications toggle, disconnect.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from config import config
from database import db
from handlers.base import admin_only, settings_keyboard, back_keyboard, cancel_keyboard
from services.userbot import userbot_manager
from scheduler.tasks import task_scheduler
from utils.logger import logger

router = Router()


class SettingsStates(StatesGroup):
    waiting_interval = State()


@router.callback_query(F.data == "settings_menu")
@admin_only
async def cb_settings_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    has_session = userbot_manager.has_session(user_id)

    text = (
        f"<b>⚙️ Settings</b>\n\n"
        f"Userbot           : {'🟢 Connected' if has_session else '🔴 Disconnected'}\n"
        f"Monitor Interval  : <b>{settings.get('monitor_interval', 60)}s</b>\n"
        f"Notifications     : {'🔔 ON' if settings.get('notifications_enabled', True) else '🔕 OFF'}\n"
        f"Max Keywords      : <b>{settings.get('max_keywords', 50)}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=settings_keyboard())
    await callback.answer()


@router.callback_query(F.data == "set_interval")
@admin_only
async def cb_set_interval(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "<b>⏱ Change Monitor Interval</b>\n\n"
        "Send the interval in seconds (minimum 30, maximum 3600).\n\n"
        "Current default: <code>60</code> seconds",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_interval)
    await callback.answer()


@router.message(SettingsStates.waiting_interval)
@admin_only
async def step_set_interval(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Please send a number (e.g. 60).")
        return
    interval = int(text)
    if interval < 30:
        await message.answer("❌ Minimum interval is 30 seconds.")
        return
    if interval > 3600:
        await message.answer("❌ Maximum interval is 3600 seconds (1 hour).")
        return
    user_id = message.from_user.id
    await db.update_settings(user_id, monitor_interval=interval)
    task_scheduler.reschedule_monitor(interval)
    await message.answer(
        f"✅ Monitor interval set to <b>{interval} seconds</b>.",
        parse_mode="HTML",
    )
    logger.info(f"Interval changed to {interval}s by admin_id={user_id}")


@router.callback_query(F.data == "toggle_notifications")
@admin_only
async def cb_toggle_notifications(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    settings = await db.get_settings(user_id)
    current = settings.get("notifications_enabled", True)
    new_val = not current
    await db.update_settings(user_id, notifications_enabled=new_val)
    status = "🔔 ON" if new_val else "🔕 OFF"
    await callback.answer(f"Notifications: {status}", show_alert=True)
    # Refresh settings menu
    settings["notifications_enabled"] = new_val
    has_session = userbot_manager.has_session(user_id)
    text = (
        f"<b>⚙️ Settings</b>\n\n"
        f"Userbot          : {'🟢 Connected' if has_session else '🔴 Disconnected'}\n"
        f"Monitor Interval : <b>{settings.get('monitor_interval', 60)}s</b>\n"
        f"Notifications    : {status}\n"
        f"Max Keywords     : <b>{settings.get('max_keywords', 50)}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=settings_keyboard())


@router.callback_query(F.data == "disconnect_userbot")
@admin_only
async def cb_disconnect_userbot(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    if not userbot_manager.has_session(user_id):
        await callback.answer("No active userbot session.", show_alert=True)
        return
    await userbot_manager.remove_session(user_id)
    await callback.message.edit_text(
        "🔌 <b>Userbot disconnected.</b>\n\nUse /setup to reconnect.",
        parse_mode="HTML",
        reply_markup=back_keyboard("main_menu"),
    )
    await callback.answer("Disconnected.")
    logger.info(f"Userbot disconnected by admin_id={user_id}")
