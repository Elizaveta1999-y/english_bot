import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
import asyncio

logger = logging.getLogger(__name__)
router = Router()

async def clear_active_mode(message: Message, state: FSMContext):
    """Чистит speaking И roleplay, если они активны."""
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    # --- SPEAKING ---
    speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
    if speaking_kb_id:
        try:
            await message.bot.delete_message(message.chat.id, speaking_kb_id)
        except Exception:
            pass
        user_state.pop("speaking_keyboard_msg_id", None)

    if user_state.get("mode") == "speaking_active":
        user_state["mode"] = ""
        user_state["keyboard_hidden"] = True
        user_state["speaking_history"] = []
        user_state["russian_streak"] = 0
        user_state["pending_feedback"] = None
        user_state["feedback_prompt_msg_id"] = None
        set_user_state(user_id, user_state)
        await state.clear()
        msg = await message.answer("Переход...", reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(0.5)
        await msg.delete()
        return  # если был speaking – ролплэй не трогаем

    # --- ROLEPLAY ---
    if user_state.get("mode") == "roleplay_active":
        reply_kb_id = user_state.get("reply_keyboard_msg_id")
        if reply_kb_id:
            try:
                await message.bot.delete_message(message.chat.id, reply_kb_id)
            except Exception:
                pass
            user_state.pop("reply_keyboard_msg_id", None)

        user_state["mode"] = ""
        user_state["roleplay_history"] = []
        user_state["russian_counter"] = 0
        user_state.pop("roleplay_goal_notified", None)
        user_state.pop("roleplay_goal_ignored", None)
        user_state.pop("voice_id", None)
        set_user_state(user_id, user_state)
        await state.clear()
        msg = await message.answer("Переход...", reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(0.5)
        await msg.delete()

@router.message(Command("support"))
async def support_start(message: Message, state: FSMContext):
    logger.info(f"✅ support_start вызван для {message.from_user.id}")

    await clear_active_mode(message, state)

    user_id = message.from_user.id
    text = (
        "Вам нужна помощь или имеются вопросы?\n"
        "Поддержка бота - support.english.bot@gmail.com\n\n"
        f"🆔 <b>Ваш ID аккаунта:</b> <code>{user_id}</code>\n\n"
        "Подробно опишите вашу ситуацию и по возможности, приложите скриншоты.\n"
        "Свяжемся с вами как можно скорее!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")