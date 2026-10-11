import logging
import asyncio
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state, get_or_create_user, start_trial_if_needed
from handlers.reading import clear_all_keyboards
from handlers.grammar import GrammarStates, finish_grammar
from handlers.words import cleanup_practice
from handlers.listening import clear_user_buttons

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
    "<b>Добро пожаловать в пространство Айвы 🇺🇸</b>\n\n"
    "Я твоя наставница в языке. Выбирай любой режим для практики, "
    "а в занятиях со мной мы понятно разберём твои ошибки, "
    "потренируемся и вместе придём к цели — свободному "
    "разговорному языку! ✨"
)


def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Занятие с Айвой", callback_data="start_tutor")],
        [InlineKeyboardButton(text="🎙️ Разговорная практика", callback_data="start_speaking")],
        [InlineKeyboardButton(text="🎬 Ролевые игры", callback_data="start_roleplay")],
        [InlineKeyboardButton(text="🎧 Тренажёры", callback_data="open_trainers")],
        [InlineKeyboardButton(text="📈 Мой прогресс", callback_data="profile_menu")],
    ])


def get_trainers_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔀 Грамматика", callback_data="start_grammar"),
            InlineKeyboardButton(text="🥇 Лексика", callback_data="start_words")
        ],
        [
            InlineKeyboardButton(text="🔉 Аудирование", callback_data="start_listening"),
            InlineKeyboardButton(text="📖 Чтение", callback_data="start_reading")
        ],
        [
            InlineKeyboardButton(text="📝 Письмо", callback_data="start_writing"),
            InlineKeyboardButton(text="🗣️ Говорение", callback_data="start_govorenie")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main_menu")],
    ])


async def _force_remove_reply_keyboard(message: Message):
    """Принудительно убирает ReplyKeyboard у пользователя."""
    try:
        await message.answer(" ", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass


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

    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    await get_or_create_user(user_id, username, first_name, last_name)

    start_trial_if_needed(user_id)

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
            await asyncio.sleep(1)
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
        tutor_kb_id = user_state.get("tutor_keyboard_msg_id")
        if tutor_kb_id:
            try:
                await bot.delete_message(chat_id, tutor_kb_id)
            except Exception:
                pass
            user_state.pop("tutor_keyboard_msg_id", None)
        keys_to_remove = [k for k in list(user_state.keys()) if k.startswith("roleplay") or k.startswith("tutor") or k in ("mode", "russian_counter", "voice_id")]
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

    # === ЯВНО убираем ReplyKeyboard ===
    await _force_remove_reply_keyboard(message)

    await show_main_menu(message, edit=False, hide_keyboard=False)


@router.callback_query(F.data == "start_lessons")
async def under_construction(callback: CallbackQuery):
    try:
        await callback.answer("Этот режим в разработке. Скоро появится! 🚧", show_alert=True)
    except Exception:
        pass
@router.callback_query(F.data == "open_trainers")
async def open_trainers(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        await callback.message.edit_text(
            "<b>🎧 Тренажёры</b>\n\n"
            "Тренируй все Hard Skills:",
            reply_markup=get_trainers_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"open_trainers: {e}")


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        await callback.message.edit_text(
            WELCOME_TEXT,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"back_to_main_menu: {e}")

async def remove_all_reply_keyboards(callback: CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    bot = callback.bot

    user_state = get_user_state(user_id)

    # Даже если режим не активен — на всякий случай убираем ReplyKeyboard
    try:
        await bot.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    if not user_state:
        return

    for key in ("speaking_keyboard_msg_id", "reply_keyboard_msg_id", "tutor_keyboard_msg_id"):
        kb_id = user_state.get(key)
        if kb_id:
            try:
                await bot.delete_message(chat_id, kb_id)
            except Exception:
                pass
            user_state.pop(key, None)

    keys_to_remove = [k for k in list(user_state.keys()) if k.startswith("roleplay") or k.startswith("speaking") or k.startswith("tutor") or k in ("mode", "russian_counter", "voice_id")]
    for k in keys_to_remove:
        user_state.pop(k, None)
    set_user_state(user_id, user_state)


# ================== ОЧИСТКА ГРАММАТИКИ ==================
async def clear_grammar_if_active(callback: CallbackQuery, state: FSMContext):
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
            except Exception:
                pass

    await state.clear()
    user_state["mode"] = ""
    set_user_state(user_id, user_state)


# ================== ОЧИСТКА ЛЕКСИКИ ==================
async def clear_words_if_active(callback: CallbackQuery, state: FSMContext):
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


# ================== ОЧИСТКА АУДИРОВАНИЯ ==================
async def clear_listening_if_active(callback: CallbackQuery, state: FSMContext):
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


# ================== ОЧИСТКА ПИСЬМА ==================
async def clear_writing_if_active(callback: CallbackQuery, state: FSMContext):
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


# ================== ОЧИСТКА ГОВОРЕНИЯ ==================
async def clear_govorenie_if_active(callback: CallbackQuery, state: FSMContext):
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


# ================== ОЧИСТКА НАСТАВНИКА ==================

async def clear_tutor_if_active(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "tutor_active":
        return

    # Сохраняем pending-сессию Наставника
    try:
        from handlers.tutor import finalize_tutor_session
        await finalize_tutor_session(
            callback.bot, callback.message.chat.id, user_id,
            is_final=False
        )
    except Exception as e:
        logger.error(f"Ошибка финализации тьютора при переходе: {e}")

    # Удаляем сообщение с Reply-клавиатурой
    tutor_kb_id = user_state.get("tutor_keyboard_msg_id")
    if tutor_kb_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, tutor_kb_id)
        except Exception:
            pass
        user_state.pop("tutor_keyboard_msg_id", None)

    user_state["mode"] = ""
    user_state.pop("tutor_voice", None)
    set_user_state(user_id, user_state)
    await state.clear()

    # Показываем секундное сообщение «Переход...» + убираем ReplyKeyboard
    try:
        msg = await callback.bot.send_message(
            callback.message.chat.id,
            "Переход...",
            reply_markup=ReplyKeyboardRemove()
        )
        await asyncio.sleep(1)
        await msg.delete()
    except Exception:
        pass
# ================== СТАРТОВЫЕ ОБРАБОТЧИКИ ==================

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
    await clear_tutor_if_active(callback, state)
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
    await clear_tutor_if_active(callback, state)
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
    await clear_tutor_if_active(callback, state)
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
    await clear_tutor_if_active(callback, state)
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
    await clear_tutor_if_active(callback, state)
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
    await clear_tutor_if_active(callback, state)
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
    await clear_tutor_if_active(callback, state)
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
    await clear_tutor_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await start_roleplay(callback, state)


@router.callback_query(F.data == "start_tutor")
async def start_tutor_mode(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_grammar_if_active(callback, state)
    await clear_words_if_active(callback, state)
    await clear_listening_if_active(callback, state)
    await clear_writing_if_active(callback, state)
    await clear_govorenie_if_active(callback, state)
    await clear_tutor_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()

    from handlers.tutor import open_tutor
    await open_tutor(callback, state)


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
    await clear_tutor_if_active(callback, state)
    await remove_all_reply_keyboards(callback)
    await state.clear()
    await show_profile(callback.message, user_id=callback.from_user.id, edit=True)


# ============== ПРОКСИ ДЛЯ КНОПОК НАСТАВНИКА ==============
@router.message(F.text == "🧠 Память")
async def memory_button_proxy(message: Message, state: FSMContext):
    user_state = get_user_state(message.from_user.id)
    if user_state.get("mode") != "tutor_active":
        return
    from handlers.tutor import show_memory
    await show_memory(message, state)


@router.message(F.text == "📊 Прогресс")
async def progress_button_proxy(message: Message, state: FSMContext):
    user_state = get_user_state(message.from_user.id)
    if user_state.get("mode") != "tutor_active":
        return
    from handlers.tutor import show_progress
    await show_progress(message, state)
# ===========================================================


@router.message(F.text == "🏠 Главное меню")
async def main_menu_text_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    current_state = await state.get_state()

    if current_state in (RoleplayStates.active.state, RoleplayStates.confirming_finish.state):
        return

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

    if user_state.get("mode") == "listening_active":
        from handlers.listening import clear_user_buttons as listening_clear_buttons
        await listening_clear_buttons(user_id, message.bot, message.chat.id)
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)

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

    if user_state.get("mode") == "tutor_active":
        tutor_kb_id = user_state.get("tutor_keyboard_msg_id")
        if tutor_kb_id:
            try:
                await message.bot.delete_message(message.chat.id, tutor_kb_id)
            except Exception:
                pass
            user_state.pop("tutor_keyboard_msg_id", None)

        try:
            from handlers.tutor import finalize_tutor_session
            await finalize_tutor_session(message.bot, message.chat.id, user_id, silent=False)
        except Exception as e:
            logger.error(f"Ошибка финализации Наставника: {e}")

        user_state["mode"] = ""
        user_state.pop("tutor_voice", None)
        set_user_state(user_id, user_state)
        await state.clear()

    if user_state.get("mode") == "roleplay_active":
        rp_kb_id = user_state.get("reply_keyboard_msg_id")
        if rp_kb_id:
            try:
                await message.bot.delete_message(message.chat.id, rp_kb_id)
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

    try:
        msg = await message.answer("Переход...", reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(1)
        await msg.delete()
    except Exception:
        pass

    # === ЯВНО убираем ReplyKeyboard перед показом меню ===
    await _force_remove_reply_keyboard(message)

    await show_main_menu(message, edit=False)