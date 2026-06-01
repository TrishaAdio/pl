"""
handlers/setup.py — /setup wizard with OTP and QR login flows.
Uses aiogram FSM for multi-step conversation state.
"""

from __future__ import annotations
import asyncio
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
)

from config import config
from database import db
from handlers.base import admin_only, setup_login_keyboard, cancel_keyboard, back_keyboard
from services.userbot import OTPLoginFlow, QRLoginFlow, userbot_manager
from utils.logger import logger

router = Router()


# ── FSM States ──

class SetupStates(StatesGroup):
    waiting_api_id    = State()
    waiting_api_hash  = State()
    choosing_method   = State()
    otp_phone         = State()
    otp_code          = State()
    otp_password      = State()
    qr_waiting        = State()


# In-memory flows keyed by admin_id
_otp_flows: dict[int, OTPLoginFlow] = {}
_qr_flows: dict[int, QRLoginFlow] = {}
_pending_api: dict[int, dict] = {}


@router.message(Command("setup"))
@admin_only
async def cmd_setup(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.clear()

    # Check if already has session
    if userbot_manager.has_session(user_id):
        await message.answer(
            "✅ <b>Userbot already connected!</b>\n\n"
            "Use /stats to check status.\n"
            "Use Settings → Disconnect to reset.",
            parse_mode="HTML",
            reply_markup=back_keyboard("main_menu"),
        )
        return

    await message.answer(
        "<b>🔧 Setup Wizard — Step 1/3</b>\n\n"
        "Please enter your <b>API ID</b>.\n\n"
        "Get it from <a href='https://my.telegram.org'>my.telegram.org</a> → "
        "App & API → App api_id",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SetupStates.waiting_api_id)


@router.message(SetupStates.waiting_api_id)
@admin_only
async def step_api_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ API ID must be a number. Please try again:", reply_markup=cancel_keyboard())
        return
    await state.update_data(api_id=int(text))
    await message.answer(
        "<b>🔧 Setup Wizard — Step 2/3</b>\n\n"
        "Now enter your <b>API HASH</b>.\n\n"
        "It's a 32-character hex string from my.telegram.org",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SetupStates.waiting_api_hash)


@router.message(SetupStates.waiting_api_hash)
@admin_only
async def step_api_hash(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) < 10:
        await message.answer("❌ API HASH looks too short. Please check and re-enter:", reply_markup=cancel_keyboard())
        return
    await state.update_data(api_hash=text)
    await message.answer(
        "<b>🔧 Setup Wizard — Step 3/3</b>\n\n"
        "Choose your <b>login method</b>:",
        parse_mode="HTML",
        reply_markup=setup_login_keyboard(),
    )
    await state.set_state(SetupStates.choosing_method)


# ── OTP LOGIN ──

@router.callback_query(F.data == "login_otp", SetupStates.choosing_method)
@admin_only
async def cb_otp_login(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    api_id = data.get("api_id")
    api_hash = data.get("api_hash")
    user_id = callback.from_user.id

    flow = OTPLoginFlow(user_id, api_id, api_hash)
    await flow.start()
    _otp_flows[user_id] = flow

    await callback.message.edit_text(
        "<b>📱 OTP Login</b>\n\nPlease enter your <b>phone number</b> with country code.\n"
        "Example: <code>+91987654321</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SetupStates.otp_phone)
    await callback.answer()


@router.message(SetupStates.otp_phone)
@admin_only
async def step_otp_phone(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    phone = message.text.strip()
    flow = _otp_flows.get(user_id)
    if not flow:
        await message.answer("⚠️ Session expired. Please /setup again.")
        await state.clear()
        return

    msg = await message.answer(f"📤 Sending code to <code>{phone}</code>...", parse_mode="HTML")
    result_msg = await flow.send_code(phone)
    await msg.edit_text(
        f"<b>📱 OTP Code</b>\n\n{result_msg}\n\n"
        "Enter the code from Telegram (format: <code>12345</code>):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await state.set_state(SetupStates.otp_code)


@router.message(SetupStates.otp_code)
@admin_only
async def step_otp_code(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    code = message.text.strip().replace(" ", "")
    flow = _otp_flows.get(user_id)
    if not flow:
        await message.answer("⚠️ Session expired. Please /setup again.")
        await state.clear()
        return

    msg = await message.answer("🔐 Verifying code...")
    success, reply_msg, session_str = await flow.submit_code(code)

    if success and session_str:
        await _finalize_session(message, state, flow, session_str, user_id, msg)
    elif flow.step == "password":
        await msg.edit_text(
            f"<b>🔐 2FA Password</b>\n\n{reply_msg}",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        await state.set_state(SetupStates.otp_password)
    else:
        await msg.edit_text(
            f"❌ {reply_msg}\n\nPlease enter the code again:",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )


@router.message(SetupStates.otp_password)
@admin_only
async def step_otp_password(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    password = message.text.strip()
    flow = _otp_flows.get(user_id)
    if not flow:
        await message.answer("⚠️ Session expired. Please /setup again.")
        await state.clear()
        return

    # Delete the password message for security
    try:
        await message.delete()
    except Exception:
        pass

    msg = await message.answer("🔐 Verifying 2FA password...")
    success, reply_msg, session_str = await flow.submit_password(password)

    if success and session_str:
        await _finalize_session(message, state, flow, session_str, user_id, msg)
    else:
        await msg.edit_text(
            f"❌ {reply_msg}\n\nTry again:",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )


# ── QR LOGIN ──

@router.callback_query(F.data == "login_qr", SetupStates.choosing_method)
@admin_only
async def cb_qr_login(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    api_id = data.get("api_id")
    api_hash = data.get("api_hash")
    user_id = callback.from_user.id

    flow = QRLoginFlow(user_id, api_id, api_hash)
    await flow.start()
    _qr_flows[user_id] = flow

    await callback.message.edit_text("⏳ Generating QR code...")
    await callback.answer()

    qr_bytes, error = await flow.generate_qr_image()
    if error or not qr_bytes:
        await callback.message.edit_text(
            f"❌ Failed to generate QR: {error}\n\nPlease /setup again."
        )
        await state.clear()
        return

    caption = (
        "<b>🔲 Scan QR Code</b>\n"
        "<blockquote>"
        "Open Telegram Settings → Devices\n"
        "Scan this QR\n"
        "Wait for authorization"
        "</blockquote>"
    )
    photo = BufferedInputFile(qr_bytes, filename="qr_login.png")
    await bot.send_photo(
        chat_id=user_id,
        photo=photo,
        caption=caption,
        parse_mode="HTML",
    )
    await state.set_state(SetupStates.qr_waiting)

    # Poll in background
    asyncio.create_task(_poll_qr_auth(bot, user_id, flow, state, data))


async def _poll_qr_auth(
    bot: Bot,
    user_id: int,
    flow: QRLoginFlow,
    state: FSMContext,
    setup_data: dict,
) -> None:
    """Background task: wait for QR scan and finalize."""
    authorized, session_str, error = await flow.wait_for_auth(timeout=120)
    if authorized and session_str:
        ok = await userbot_manager.add_session(
            admin_id=user_id,
            api_id=setup_data["api_id"],
            api_hash=setup_data["api_hash"],
            session_string=session_str,
        )
        if ok:
            await bot.send_message(
                user_id,
                "<b>✅ Userbot Connected</b>\n"
                "<blockquote>"
                "Session Created\n"
                "Userbot Online\n"
                "Monitoring Enabled"
                "</blockquote>",
                parse_mode="HTML",
            )
            logger.setup(f"QR login success for admin_id={user_id}")
        else:
            await bot.send_message(user_id, "⚠️ Session created but connection failed. Try /setup again.")
    else:
        await bot.send_message(user_id, f"❌ QR login failed: {error}\n\nUse /setup to try again.")
    await state.clear()
    _qr_flows.pop(user_id, None)
    await flow.cleanup()


# ── Cancel ──

@router.callback_query(F.data.in_({"cancel_action", "cancel_setup"}))
@admin_only
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    # Cleanup flows
    if user_id in _otp_flows:
        await _otp_flows.pop(user_id).cleanup()
    if user_id in _qr_flows:
        _qr_flows[user_id].cancel()
        await _qr_flows.pop(user_id).cleanup()
    await state.clear()
    await callback.message.edit_text(
        "❌ Setup cancelled. Use /setup to start again.",
        reply_markup=back_keyboard("main_menu"),
    )
    await callback.answer("Cancelled.")


# ── Helpers ──

async def _finalize_session(
    message: Message,
    state: FSMContext,
    flow: OTPLoginFlow,
    session_str: str,
    user_id: int,
    msg: Message,
) -> None:
    """Save session, connect userbot, notify user."""
    data = await state.get_data()
    api_id = data.get("api_id")
    api_hash = data.get("api_hash")

    ok = await userbot_manager.add_session(
        admin_id=user_id,
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_str,
        phone=flow.phone,
    )

    if ok:
        await msg.edit_text(
            "<b>✅ Userbot Connected</b>\n"
            "<blockquote>"
            "Session Created\n"
            "Userbot Online\n"
            "Monitoring Enabled"
            "</blockquote>",
            parse_mode="HTML",
        )
        logger.setup(f"OTP login success for admin_id={user_id}")
    else:
        await msg.edit_text("⚠️ Session saved but connection failed. Try /setup again.")

    await state.clear()
    _otp_flows.pop(user_id, None)
    await flow.cleanup()
