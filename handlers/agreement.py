import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
import asyncio

logger = logging.getLogger(__name__)
router = Router()

async def clear_active_mode(message: Message, state: FSMContext):
    """Чистит ЛЮБОЙ активный режим."""
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")

    # --- ЧТЕНИЕ ---
    if mode == "reading_active":
        data = await state.get_data()
        for key in ("last_task_msg_id", "progress_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(
                        chat_id=message.chat.id, message_id=msg_id, reply_markup=None
                    )
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.")
        return

    if mode == "speaking_active":
        speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
        if speaking_kb_id:
            try:
                await message.bot.delete_message(message.chat.id, speaking_kb_id)
            except Exception:
                pass
            user_state.pop("speaking_keyboard_msg_id", None)
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
        return

    if mode == "roleplay_active":
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
        return

    if mode == "grammar_active":
        data = await state.get_data()
        for key in ("task_msg_id", "progress_msg_id", "revision_msg_id", "revision_header_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=msg_id, reply_markup=None)
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "words_active":
        from handlers.words import user_message_ids, user_sessions, remove_buttons_from_messages
        if user_id in user_message_ids:
            msg_ids = list(user_message_ids[user_id].values())
            await remove_buttons_from_messages(message.bot, message.chat.id, msg_ids)
            user_message_ids[user_id] = {}
        user_sessions.pop(user_id, None)
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "listening_active":
        from handlers.listening import clear_user_buttons
        await clear_user_buttons(user_id, message.bot, message.chat.id)
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "writing_active":
        data = await state.get_data()
        for key in ("progress_msg_id", "last_task_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=msg_id, reply_markup=None)
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "govorenie_active":
        data = await state.get_data()
        for key in ("progress_msg_id", "last_task_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=msg_id, reply_markup=None)
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

@router.message(Command("agreement"))
async def agreement_command(message: Message, state: FSMContext):
    await clear_active_mode(message, state)

    text = (
        "<b>Пользовательское соглашение и другие документы</b>\n\n"
        "Все официальные документы доступны в одной папке:\n"
        "🔗 <a href='https://disk.yandex.ru/d/b0CooYtb5OxXgQ'>Открыть папку с документами</a>\n\n"
        "Ознакомьтесь с условиями использования, политикой конфиденциальности и тарифами."
    )
    await message.answer(text, parse_mode="HTML")