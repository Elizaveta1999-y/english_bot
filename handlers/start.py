import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
from handlers.reading import clear_all_keyboards
from handlers.grammar import GrammarStates, finish_grammar
from handlers.words import cleanup_practice
from handlers.listening import clear_user_buttons
import asyncio

from handlers.speaking import start_speaking
from handlers.reading import start_reading
from handlers.words import start_words
from handlers.listening import start_listening
from handlers.grammar import start_grammar
from handlers.writing import start_writing
from handlers.govorenie import start_govorenie
from handlers.roleplay import start_roleplay
from handlers.profile import show_profile

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
    "Общайся голосом со своим персональным AI-тьютором и практикуй Hard Skills в любое время! 🧠\n"
    "Выбирай режим и начни совершенствоваться в языке!\n\n"
)

def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎙️ Общение с AI", callback_data="start_speaking"),
            InlineKeyboardButton(text="🎬 Ролевые игры", callback_data="start_roleplay")
        ],
        [
            InlineKeyboardButton(text="🔀 Грамматика", callback_data="start_grammar"),
            InlineKeyboardButton(text="🥇 Лексика", callback_data="start_words")
        ],
        [
            InlineKeyboardButton(text="🔉 Аудирование", callback_data="start_listening"),
            InlineKeyboardButton(text="📝 Письмо", callback_data="start_writing")
        ],
        [
            InlineKeyboardButton(text="📖 Чтение", callback_data="start_reading"),
            InlineKeyboardButton(text="🗣️ Говорение", callback_data="start_govorenie")
        ],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="profile_menu")]
    ])

async def show_main_menu(message: Message, edit: bool = False, hide_keyboard: bool = False):
    if hide_keyboard:
        try:
            await message.answer(" ", reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass

    keyboard = get_main_menu_keyboard()
    if edit:
        await message.edit_text(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    bot = message.bot
    chat_id = message.chat.id

    await cleanup_practice(user_id, bot, chat_id, send_message=False)

    current_state = await state.get_state()
    if current_state in (GrammarStates.choosing_type.state, GrammarStates.waiting_for_text.state, GrammarStates.in_progress.state):
        await finish_grammar(message, state, bot)
        await show_main_menu(message, edit=False)
        return

    user_state = get_user_state(user_id)
    if user_state:
        if user_state.get("mode") == "speaking_active":
            user_state["mode"] = ""
            user_state["keyboard_hidden"] = True
            user_state["pending_feedback"] = None
            user_state["feedback_prompt_msg_id"] = None
            set_user_state(user_id, user_state)
            await state.clear()

    # Удаляем клавиатуры (speaking и roleplay)
    if user_state:
        # Speaking клавиатура
        speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
        if speaking_kb_id:
            try:
                await bot.delete_message(chat_id, speaking_kb_id)
            except Exception:
                pass
            user_state.pop("speaking_keyboard_msg_id", None)
        # Roleplay клавиатура
        keyboard_msg_id = user_state.get("reply_keyboard_msg_id")
        if keyboard_msg_id:
            try:
                await bot.delete_message(chat_id, keyboard_msg_id)
            except Exception:
                pass
            user_state.pop("reply_keyboard_msg_id", None)
        # Очищаем все ключи ролевой игры
        keys_to_remove = [k for k in list(user_state.keys()) if k.startswith("roleplay") or k in ("mode", "russian_counter", "voice_id")]
        for k in keys_to_remove:
            user_state.pop(k, None)
        set_user_state(user_id, user_state)

    await clear_all_keyboards(message, state)
    if not user_state:
        set_user_state(user_id, {})

    await state.clear()
    await clear_user_buttons(user_id, bot, chat_id)

    user_state = get_user_state(user_id)
    hide_kb = user_state.get("keyboard_hidden", False) if user_state else False
    if hide_kb:
        user_state["keyboard_hidden"] = False
        set_user_state(user_id, user_state)

    await show_main_menu(message, edit=False, hide_keyboard=hide_kb)


@router.callback_query(F.data == "start_lessons")
async def under_construction(callback: CallbackQuery):
    try:
        await callback.answer("Этот режим в разработке. Скоро появится! 🚧", show_alert=True)
    except Exception:
        pass


async def remove_all_reply_keyboards(callback: CallbackQuery):
    """Удаляет клавиатуры ролевой игры и speaking, если они есть. Очищает состояние."""
    logger.info(f"🔹 remove_all_reply_keyboards вызвана для user {callback.from_user.id}")
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    bot = callback.bot
    
    user_state = get_user_state(user_id)
    if not user_state:
        logger.info("🔹 user_state пуст, выход")
        return
    
    is_active = (
        user_state.get("mode") in ("speaking_active", "roleplay_active") or
        user_state.get("reply_keyboard_msg_id") is not None or
        user_state.get("speaking_keyboard_msg_id") is not None
    )
    
    if not is_active:
        logger.info("🔹 Активных режимов с Reply-клавиатурой нет, выход")
        return
    
    logger.info(f"🔹 Активный режим: {user_state.get('mode')}, удаляю клавиатуры")
    
    # Отправляем "Переход..." с удалением клавиатуры
    try:
        temp_msg = await bot.send_message(chat_id, "Переход...", reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(0.1)
        await bot.delete_message(chat_id, temp_msg.message_id)
        logger.info("🔹 Сообщение 'Переход...' отправлено и удалено")
    except Exception as e:
        logger.error(f"🔹 Ошибка при отправке/удалении 'Переход...': {e}")
    
    # Удаляем сообщение с клавиатурой speaking
    speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
    if speaking_kb_id:
        try:
            await bot.delete_message(chat_id, speaking_kb_id)
            logger.info(f"🔹 Удалено сообщение speaking с клавиатурой (ID {speaking_kb_id})")
        except Exception as e:
            logger.error(f"🔹 Не удалось удалить speaking клавиатуру: {e}")
        user_state.pop("speaking_keyboard_msg_id", None)
    
    # Удаляем сообщение с клавиатурой roleplay
    roleplay_kb_id = user_state.get("reply_keyboard_msg_id")
    if roleplay_kb_id:
        try:
            await bot.delete_message(chat_id, roleplay_kb_id)
            logger.info(f"🔹 Удалено сообщение roleplay с клавиатурой (ID {roleplay_kb_id})")
        except Exception as e:
            logger.error(f"🔹 Не удалось удалить roleplay клавиатуру: {e}")
        user_state.pop("reply_keyboard_msg_id", None)
    
    # Очищаем все ключи обоих режимов
    keys_to_remove = [k for k in list(user_state.keys()) if k.startswith("roleplay") or k.startswith("speaking") or k in ("mode", "russian_counter", "voice_id")]
    for k in keys_to_remove:
        user_state.pop(k, None)
    set_user_state(user_id, user_state)
    logger.info("🔹 Ключи режимов очищены")


# ---------- ОБРАБОТЧИКИ ВСЕХ РЕЖИМОВ (с удалением клавиатур и сбросом FSM) ----------
@router.callback_query(F.data == "start_speaking")
async def start_speaking_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_speaking_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    logger.info("🔹 FSM сброшен, вызываю start_speaking")
    await start_speaking(callback, state)


@router.callback_query(F.data == "start_reading")
async def start_reading_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_reading_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_reading(callback, state)


@router.callback_query(F.data == "start_writing")
async def start_writing_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_writing_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_writing(callback, state)


@router.callback_query(F.data == "start_govorenie")
async def start_govorenie_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_govorenie_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_govorenie(callback, state)


@router.callback_query(F.data == "start_grammar")
async def start_grammar_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_grammar_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_grammar(callback, state)


@router.callback_query(F.data == "start_words")
async def start_words_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_words_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_words(callback, state)


@router.callback_query(F.data == "start_listening")
async def start_listening_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_listening_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_listening(callback, state)


@router.callback_query(F.data == "profile_menu")
async def start_profile_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_profile_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await show_profile(callback.message, user_id=callback.from_user.id, edit=True)


@router.callback_query(F.data == "start_roleplay")
async def start_roleplay_mode(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔹 start_roleplay_mode вызван для user {callback.from_user.id}")
    try:
        await callback.answer()
    except Exception:
        pass
    # Очищаем состояние ролевой игры (и speaking), если есть
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state:
        speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
        if speaking_kb_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, speaking_kb_id)
            except Exception:
                pass
            user_state.pop("speaking_keyboard_msg_id", None)
        keyboard_msg_id = user_state.get("reply_keyboard_msg_id")
        if keyboard_msg_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, keyboard_msg_id)
            except Exception:
                pass
            user_state.pop("reply_keyboard_msg_id", None)
        keys_to_remove = [k for k in list(user_state.keys()) if k.startswith("roleplay") or k.startswith("speaking") or k in ("mode", "russian_counter", "voice_id")]
        for k in keys_to_remove:
            user_state.pop(k, None)
        set_user_state(user_id, user_state)
    await state.clear()
    await start_roleplay(callback)