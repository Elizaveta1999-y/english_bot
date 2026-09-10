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

from handlers.roleplay import RoleplayStates
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
    "Общайся голосом со своим AI-тьютором, практикуй реальные ситуации и оттачивай главные навыки языка! 🧠\n"
    "Выбирай режим и начинай совершенствоваться в языке!\n\n"
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
            
            msg = await message.answer("Переход...", reply_markup=ReplyKeyboardRemove())
            await asyncio.sleep(0.5)
            await msg.delete()

    if user_state:
        speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
        if speaking_kb_id:
            try:
                await bot.delete_message(chat_id, speaking_kb_id)
            except Exception:
                pass
            user_state.pop("speaking_keyboard_msg_id", None)
        keyboard_msg_id = user_state.get("reply_keyboard_msg_id")
        if keyboard_msg_id:
            try:
                await bot.delete_message(chat_id, keyboard_msg_id)
            except Exception:
                pass
            user_state.pop("reply_keyboard_msg_id", None)
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
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    bot = callback.bot
    
    user_state = get_user_state(user_id)
    if not user_state:
        return
    
    is_active = (
        user_state.get("mode") in ("speaking_active", "roleplay_active") or
        user_state.get("reply_keyboard_msg_id") is not None or
        user_state.get("speaking_keyboard_msg_id") is not None
    )
    
    if not is_active:
        return
    
    try:
        msg = await bot.send_message(chat_id, "Переход...", reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(0.5)
        await msg.delete()
    except Exception:
        pass
    
    speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
    if speaking_kb_id:
        try:
            await bot.delete_message(chat_id, speaking_kb_id)
        except Exception:
            pass
        user_state.pop("speaking_keyboard_msg_id", None)
    
    roleplay_kb_id = user_state.get("reply_keyboard_msg_id")
    if roleplay_kb_id:
        try:
            await bot.delete_message(chat_id, roleplay_kb_id)
        except Exception:
            pass
        user_state.pop("reply_keyboard_msg_id", None)
    
    keys_to_remove = [k for k in list(user_state.keys()) if k.startswith("roleplay") or k.startswith("speaking") or k in ("mode", "russian_counter", "voice_id")]
    for k in keys_to_remove:
        user_state.pop(k, None)
    set_user_state(user_id, user_state)

# ================== ОЧИСТКА ГРАММАТИКИ ПРИ ПЕРЕХОДЕ ==================
async def clear_grammar_if_active(callback: CallbackQuery, state: FSMContext):
    """Убирает кнопки грамматики и сбрасывает состояние, если режим грамматики активен."""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "grammar_active":
        return
    
    data = await state.get_data()
    for key in ("task_msg_id", "progress_msg_id", "revision_msg_id", "revision_header_msg_id"):
        msg_id = data.get(key)
        if msg_id:
            try:
                await callback.bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=msg_id,
                    reply_markup=None
                )
                logger.info(f"[clear_grammar_if_active] Кнопки убраны у {key}={msg_id}")
            except Exception as e:
                logger.warning(f"[clear_grammar_if_active] Не удалось убрать кнопки у {msg_id}: {e}")
    
    await state.clear()
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    logger.info("[clear_grammar_if_active] Режим грамматики очищен")
# =====================================================================

# ================== ОЧИСТКА ЛЕКСИКИ ПРИ ПЕРЕХОДЕ ==================
async def clear_words_if_active(callback: CallbackQuery, state: FSMContext):
    """Убирает кнопки лексики и сбрасывает состояние, если режим лексики активен."""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "words_active":
        return
    
    from handlers.words import user_message_ids, user_sessions, remove_buttons_from_messages
    
    chat_id = callback.message.chat.id
    if user_id in user_message_ids:
        msg_ids = list(user_message_ids[user_id].values())
        await remove_buttons_from_messages(callback.bot, chat_id, msg_ids)
        user_message_ids[user_id] = {}
    
    user_sessions.pop(user_id, None)
    
    await state.clear()
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    logger.info("[clear_words_if_active] Режим лексики очищен")
# ==================================================================

# ================== ОЧИСТКА АУДИРОВАНИЯ ПРИ ПЕРЕХОДЕ ==================
async def clear_listening_if_active(callback: CallbackQuery, state: FSMContext):
    """Убирает кнопки аудирования и сбрасывает состояние, если режим аудирования активен."""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "listening_active":
        return
    
    from handlers.listening import clear_user_buttons as listening_clear_buttons
    
    chat_id = callback.message.chat.id
    await listening_clear_buttons(user_id, callback.bot, chat_id)
    
    await state.clear()
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    logger.info("[clear_listening_if_active] Режим аудирования очищен")
# ======================================================================

# ================== ОЧИСТКА ПИСЬМА ПРИ ПЕРЕХОДЕ ==================
async def clear_writing_if_active(callback: CallbackQuery, state: FSMContext):
    """Убирает кнопки письма и сбрасывает состояние, если режим письма активен."""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "writing_active":
        return
    
    chat_id = callback.message.chat.id
    data = await state.get_data()
    
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    
    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    
    await state.clear()
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    logger.info("[clear_writing_if_active] Режим письма очищен")
# ==================================================================

# ================== ОЧИСТКА ГОВОРЕНИЯ ПРИ ПЕРЕХОДЕ ==================
async def clear_govorenie_if_active(callback: CallbackQuery, state: FSMContext):
    """Убирает кнопки говорения и сбрасывает состояние, если режим говорения активен."""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "govorenie_active":
        return
    
    chat_id = callback.message.chat.id
    data = await state.get_data()
    
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    
    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    
    await state.clear()
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    logger.info("[clear_govorenie_if_active] Режим говорения очищен")
# =====================================================================

@router.callback_query(F.data == "start_speaking")
async def start_speaking_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_speaking(callback, state)

@router.callback_query(F.data == "start_reading")
async def start_reading_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_reading(callback, state)

@router.callback_query(F.data == "start_writing")
async def start_writing_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_writing(callback, state)

@router.callback_query(F.data == "start_govorenie")
async def start_govorenie_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_govorenie(callback, state)

@router.callback_query(F.data == "start_grammar")
async def start_grammar_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_grammar(callback, state)

@router.callback_query(F.data == "start_words")
async def start_words_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_words(callback, state)

@router.callback_query(F.data == "start_listening")
async def start_listening_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_listening(callback, state)

@router.callback_query(F.data == "start_roleplay")
async def start_roleplay_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_roleplay(callback)

@router.callback_query(F.data == "profile_menu")
async def start_profile_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await show_profile(callback.message, user_id=callback.from_user.id, edit=False)

@router.message(F.text == "🏠 Главное меню")
async def main_menu_text_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    
    current_state = await state.get_state()
    if current_state in (RoleplayStates.active.state, RoleplayStates.confirming_finish.state):
        return
    
    # Очистка грамматики если активна
    if user_state.get("mode") == "grammar_active":
        data = await state.get_data()
        for key in ("task_msg_id", "progress_msg_id", "revision_msg_id", "revision_header_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(
                        chat_id=message.chat.id,
                        message_id=msg_id,
                        reply_markup=None
                    )
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
    
    # Очистка лексики если активна
    if user_state.get("mode") == "words_active":
        from handlers.words import user_message_ids, user_sessions, remove_buttons_from_messages
        if user_id in user_message_ids:
            msg_ids = list(user_message_ids[user_id].values())
            await remove_buttons_from_messages(message.bot, message.chat.id, msg_ids)
            user_message_ids[user_id] = {}
        user_sessions.pop(user_id, None)
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
    
    # Очистка аудирования если активно
    if user_state.get("mode") == "listening_active":
        from handlers.listening import clear_user_buttons as listening_clear_buttons
        await listening_clear_buttons(user_id, message.bot, message.chat.id)
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
    
    # Очистка письма если активно
    if user_state.get("mode") == "writing_active":
        data = await state.get_data()
        progress_msg_id = data.get("progress_msg_id")
        if progress_msg_id:
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=progress_msg_id,
                    reply_markup=None
                )
            except Exception:
                pass
        last_msg_id = data.get("last_task_msg_id")
        if last_msg_id:
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=last_msg_id,
                    reply_markup=None
                )
            except Exception:
                pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
    
    # Очистка говорения если активно
    if user_state.get("mode") == "govorenie_active":
        data = await state.get_data()
        progress_msg_id = data.get("progress_msg_id")
        if progress_msg_id:
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=progress_msg_id,
                    reply_markup=None
                )
            except Exception:
                pass
        last_msg_id = data.get("last_task_msg_id")
        if last_msg_id:
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=last_msg_id,
                    reply_markup=None
                )
            except Exception:
                pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
    
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
    
    await show_main_menu(message, edit=False)