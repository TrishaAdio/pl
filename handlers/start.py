"""
handlers/start.py — /start, /help, /ping, /stats, main menu callbacks
"""

from __future__ import annotations
import time

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from config import config
from database import db
from handlers.base import admin_only, main_menu_keyboard, back_keyboard
from services.userbot import userbot_manager
from scheduler.tasks import task_scheduler
from utils.helpers import format_utc, utc_now
from utils.logger import logger

router = Router()

_start_time = time.time()


@router.message(Command("start"))
@admin_only
async def cmd_start(message: Message) -> None:
    user = message.from_user
    await db.upsert_admin(user.id, user.username, user.first_name)

    has_session = userbot_manager.has_session(user.id)
    status_line = "🟢 Userbot Connected" if has_session else "🔴 Userbot Not Connected"

    text = (
        f"<b>👋 Welcome, {user.first_name}!</b>\n\n"
        f"<b>TG Monitor</b> — Keyword Search Monitor\n\n"
        f"Status: {status_line}\n\n"
        f"Use /setup to connect your Telegram account.\n"
        f"Use /keywords to manage monitoring keywords.\n"
        f"Use /help for all commands."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())


@router.message(Command("help"))
@admin_only
async def cmd_help(message: Message) -> None:
    text = (
        "<b>📖 TG Monitor — Commands</b>\n\n"
        "<b>Setup</b>\n"
        "/setup — Connect Telegram userbot\n\n"
        "<b>Keywords</b>\n"
        "/keyword &lt;text&gt; — Add a keyword\n"
        "/delkeyword &lt;text&gt; — Remove a keyword\n"
        "/keywords — List all keywords\n\n"
        "<b>Monitor</b>\n"
        "/stats — Show statistics\n"
        "/logs — Recent activity logs\n"
        "/export — Export keywords as text\n"
        "/import — Import keywords (send list)\n\n"
        "<b>System</b>\n"
        "/ping — Check bot response time\n"
        "/restart — Restart monitoring job\n"
        "/help — This message"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=back_keyboard("main_menu"))


@router.message(Command("ping"))
@admin_only
async def cmd_ping(message: Message) -> None:
    t0 = time.time()
    sent = await message.answer("🏓 Pong!")
    elapsed_ms = round((time.time() - t0) * 1000, 1)
    uptime_s = int(time.time() - _start_time)
    h, rem = divmod(uptime_s, 3600)
    m, s = divmod(rem, 60)
    uptime_str = f"{h}h {m}m {s}s"

    await sent.edit_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"Response : <code>{elapsed_ms}ms</code>\n"
        f"Uptime   : <code>{uptime_str}</code>\n"
        f"Schedule : <code>{'Running' if task_scheduler.is_running() else 'Stopped'}</code>",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
@admin_only
async def cmd_stats(message: Message) -> None:
    user_id = message.from_user.id
    stats = await db.get_stats(user_id)

    session_info = "🟢 Connected"
    if not stats["has_session"]:
        session_info = "🔴 Not Connected"
    elif stats.get("session_phone"):
        session_info = f"🟢 {stats['session_phone']}"

    text = (
        f"<b>📊 Statistics</b>\n\n"
        f"Userbot     : {session_info}\n"
        f"Keywords    : <b>{stats['keywords']}</b> / {config.MAX_KEYWORDS}\n"
        f"Alerts      : <b>{stats['alerts']}</b>\n"
        f"Snapshots   : <b>{stats['snapshots']}</b>\n"
        f"Monitor Job : <code>{'✅ Active' if task_scheduler.is_running() else '❌ Stopped'}</code>\n"
        f"Next Run    : <code>{task_scheduler.get_job_info() or 'N/A'}</code>\n"
        f"Time        : <code>{format_utc(utc_now())}</code>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())


@router.message(Command("restart"))
@admin_only
async def cmd_restart(message: Message) -> None:
    msg = await message.answer("♻️ Restarting monitor job...")
    task_scheduler.remove_monitor_job()
    task_scheduler.add_monitor_job()
    await msg.edit_text("✅ <b>Monitor job restarted!</b>", parse_mode="HTML")
    logger.info(f"Monitor job restarted by admin_id={message.from_user.id}")


@router.message(Command("logs"))
@admin_only
async def cmd_logs(message: Message) -> None:
    logs = await db.get_recent_logs(limit=15)
    if not logs:
        await message.answer("📭 No logs yet.")
        return

    lines = []
    for entry in reversed(logs):
        ts = entry.get("created_at")
        if hasattr(ts, "strftime"):
            ts_str = ts.strftime("%H:%M:%S")
        else:
            ts_str = "??:??:??"
        level = entry.get("level", "INFO")
        msg = entry.get("message", "")[:80]
        lines.append(f"<code>[{ts_str}] [{level}]</code> {msg}")

    text = "<b>📋 Recent Logs</b>\n\n" + "\n".join(lines)
    await message.answer(text, parse_mode="HTML")


# ── Inline callbacks ──

@router.callback_query(F.data == "main_menu")
@admin_only
async def cb_main_menu(callback: CallbackQuery) -> None:
    has_session = userbot_manager.has_session(callback.from_user.id)
    status = "🟢 Connected" if has_session else "🔴 Not Connected"
    await callback.message.edit_text(
        f"<b>🏠 Main Menu</b>\n\nUserbot: {status}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "refresh_status")
@admin_only
async def cb_refresh(callback: CallbackQuery) -> None:
    stats = await db.get_stats(callback.from_user.id)
    has_session = userbot_manager.has_session(callback.from_user.id)
    status = "🟢 Connected" if has_session else "🔴 Not Connected"
    await callback.message.edit_text(
        f"<b>🔄 Status Refreshed</b>\n\n"
        f"Userbot : {status}\n"
        f"Keywords: {stats['keywords']}\n"
        f"Alerts  : {stats['alerts']}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Refreshed!")


@router.callback_query(F.data == "show_stats")
@admin_only
async def cb_stats(callback: CallbackQuery) -> None:
    stats = await db.get_stats(callback.from_user.id)
    session_info = "🟢 Connected" if stats["has_session"] else "🔴 Not Connected"
    text = (
        f"<b>📊 Statistics</b>\n\n"
        f"Userbot  : {session_info}\n"
        f"Keywords : <b>{stats['keywords']}</b> / {config.MAX_KEYWORDS}\n"
        f"Alerts   : <b>{stats['alerts']}</b>\n"
        f"Snapshots: <b>{stats['snapshots']}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_keyboard("main_menu"))
    await callback.answer()
