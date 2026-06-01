"""
handlers/keywords.py — Keyword add/remove/list commands and inline callbacks.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from database import db
from handlers.base import admin_only, back_keyboard, cancel_keyboard
from utils.helpers import is_valid_keyword, utc_now, truncate
from utils.logger import logger

router = Router()


class KeywordStates(StatesGroup):
    adding   = State()
    removing = State()
    importing = State()


# ── /keyword <text> ──

@router.message(Command("keyword"))
@admin_only
async def cmd_add_keyword(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "❌ Usage: <code>/keyword &lt;text&gt;</code>\n\nExample: <code>/keyword Hyderabad News</code>",
            parse_mode="HTML",
        )
        return
    keyword = parts[1].strip()
    await _do_add_keyword(message, keyword)


@router.message(Command("delkeyword"))
@admin_only
async def cmd_del_keyword(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "❌ Usage: <code>/delkeyword &lt;text&gt;</code>",
            parse_mode="HTML",
        )
        return
    keyword = parts[1].strip()
    user_id = message.from_user.id
    deleted = await db.delete_keyword(user_id, keyword)
    if deleted:
        await message.answer(f"✅ Keyword removed: <code>{keyword}</code>", parse_mode="HTML")
        logger.info(f"Keyword '{keyword}' deleted by admin_id={user_id}")
    else:
        await message.answer(f"❌ Keyword not found: <code>{keyword}</code>", parse_mode="HTML")


@router.message(Command("keywords"))
@admin_only
async def cmd_list_keywords(message: Message) -> None:
    user_id = message.from_user.id
    keywords = await db.get_keywords(user_id)
    await _send_keywords_list(message, user_id, keywords)


# ── /export ──

@router.message(Command("export"))
@admin_only
async def cmd_export_keywords(message: Message) -> None:
    user_id = message.from_user.id
    keywords = await db.get_keywords(user_id)
    if not keywords:
        await message.answer("📭 No keywords to export.")
        return
    lines = [kw["keyword"] for kw in keywords]
    text = "\n".join(lines)
    await message.answer(
        f"<b>📤 Export ({len(lines)} keywords)</b>\n\n<pre>{text}</pre>",
        parse_mode="HTML",
    )


# ── /import ──

@router.message(Command("import"))
@admin_only
async def cmd_import_keywords(message: Message, state: FSMContext) -> None:
    await message.answer(
        "<b>📥 Import Keywords</b>\n\n"
        "Send a message with one keyword per line.\n"
        "Example:\n<pre>Hyderabad News\nMumbai Weather\nDelhi Tech</pre>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(KeywordStates.importing)


@router.message(KeywordStates.importing)
@admin_only
async def step_import(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    lines = [l.strip() for l in message.text.splitlines() if l.strip()]
    added, skipped, errors = 0, 0, 0
    for kw in lines:
        if not is_valid_keyword(kw):
            errors += 1
            continue
        try:
            result = await db.add_keyword(user_id, kw)
            if result:
                added += 1
            else:
                skipped += 1
        except ValueError:
            errors += 1
    await message.answer(
        f"<b>📥 Import Complete</b>\n\n"
        f"✅ Added  : {added}\n"
        f"⏩ Skipped: {skipped}\n"
        f"❌ Errors : {errors}",
        parse_mode="HTML",
    )
    await state.clear()
    logger.info(f"Import: added={added} skipped={skipped} errors={errors} for admin_id={user_id}")


# ── Inline: add_keyword ──

@router.callback_query(F.data == "add_keyword")
@admin_only
async def cb_add_keyword(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "<b>➕ Add Keyword</b>\n\nSend the keyword to monitor.\n"
        "Example: <code>Hyderabad News</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(KeywordStates.adding)
    await callback.answer()


@router.message(KeywordStates.adding)
@admin_only
async def step_add_keyword(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _do_add_keyword(message, message.text.strip())


# ── Inline: remove_keyword ──

@router.callback_query(F.data == "remove_keyword")
@admin_only
async def cb_remove_keyword(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    keywords = await db.get_keywords(user_id)
    if not keywords:
        await callback.message.edit_text(
            "📭 No keywords to remove.",
            reply_markup=back_keyboard("main_menu"),
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for kw in keywords:
        label = truncate(kw["keyword"], 30)
        builder.button(
            text=f"🗑 {label}",
            callback_data=f"delkw:{kw['keyword'][:64]}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu"))

    await callback.message.edit_text(
        "<b>🗑 Select keyword to remove:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delkw:"))
@admin_only
async def cb_do_delete_keyword(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    keyword = callback.data.removeprefix("delkw:")
    deleted = await db.delete_keyword(user_id, keyword)
    if deleted:
        await callback.answer(f"✅ Removed: {keyword}", show_alert=True)
    else:
        await callback.answer("❌ Not found or already removed.", show_alert=True)
    # Refresh list
    keywords = await db.get_keywords(user_id)
    if not keywords:
        await callback.message.edit_text(
            "📭 No more keywords.",
            reply_markup=back_keyboard("main_menu"),
        )
        return
    builder = InlineKeyboardBuilder()
    for kw in keywords:
        label = truncate(kw["keyword"], 30)
        builder.button(text=f"🗑 {label}", callback_data=f"delkw:{kw['keyword'][:64]}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu"))
    await callback.message.edit_text(
        "<b>🗑 Select keyword to remove:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


# ── Inline: list_keywords ──

@router.callback_query(F.data == "list_keywords")
@admin_only
async def cb_list_keywords(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    keywords = await db.get_keywords(user_id)
    text, markup = _build_keywords_text(keywords, user_id)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()


# ── Helpers ──

async def _do_add_keyword(message: Message, keyword: str) -> None:
    user_id = message.from_user.id
    if not is_valid_keyword(keyword):
        await message.answer("❌ Invalid keyword. Must be 1–200 characters.", parse_mode="HTML")
        return
    try:
        added = await db.add_keyword(user_id, keyword)
        if added:
            await message.answer(
                f"✅ <b>Keyword added:</b> <code>{keyword}</code>\n\n"
                f"Monitoring will start within {config.MONITOR_INTERVAL} seconds.",
                parse_mode="HTML",
            )
            logger.info(f"Keyword '{keyword}' added by admin_id={user_id}")
        else:
            await message.answer(
                f"⏩ Already exists: <code>{keyword}</code>",
                parse_mode="HTML",
            )
    except ValueError as e:
        await message.answer(f"❌ {e}", parse_mode="HTML")


def _build_keywords_text(keywords: list, user_id: int) -> tuple:
    if not keywords:
        return "📭 <b>No keywords yet.</b>\n\nUse /keyword to add one.", back_keyboard("main_menu")
    lines = []
    for i, kw in enumerate(keywords, 1):
        ts = kw.get("created_at")
        ts_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else "—"
        lines.append(f"{i}. <code>{kw['keyword']}</code> <i>({ts_str})</i>")
    text = (
        f"<b>📋 Keywords ({len(keywords)}/{config.MAX_KEYWORDS})</b>\n\n"
        + "\n".join(lines)
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add", callback_data="add_keyword")
    builder.button(text="🗑 Remove", callback_data="remove_keyword")
    builder.button(text="⬅️ Back", callback_data="main_menu")
    builder.adjust(2, 1)
    return text, builder.as_markup()


async def _send_keywords_list(message: Message, user_id: int, keywords: list) -> None:
    text, markup = _build_keywords_text(keywords, user_id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)
