import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("support"))
async def support_start(message: Message, state: FSMContext):
    logger.info(f"✅ support_start вызван для {message.from_user.id}")

    # ===== ПОЛНАЯ ОЧИСТКА SPEAKING (КАК В РОЛЕВОЙ ИГРЕ) =====
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    
    # Удаляем сообщение с клавиатурой speaking
    keyboard_msg_id = user_state.get("speaking_keyboard_msg_id")
    if keyboard_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, keyboard_msg_id)
        except Exception:
            pass
        user_state.pop("speaking_keyboard_msg_id", None)
    
    # Сбрасываем режим speaking
    if user_state.get("mode") == "speaking_active":
        user_state["mode"] = ""
        user_state["keyboard_hidden"] = True
        user_state["speaking_history"] = []
        user_state["russian_streak"] = 0
        user_state["pending_feedback"] = None
        user_state["feedback_prompt_msg_id"] = None
        set_user_state(user_id, user_state)
        await state.clear()
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())

    # ===== ОСНОВНАЯ ЛОГИКА ПОДДЕРЖКИ =====
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