import os
import json
import re
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.db import (
    get_user_stats_db, update_user_stats_db, reset_user_stats_db,
    add_reading_error_db, remove_reading_error_db, get_reading_errors_db, clear_reading_errors_db,
    get_progress_index, set_progress_index, reset_progress_index,
)

logger = logging.getLogger(__name__)
router = Router()

# ---------- Конфигурация ----------
WORDS_DIR = "data/words/"
META_FILE = "data/categories_meta.json"

os.makedirs(WORDS_DIR, exist_ok=True)

try:
    with open(META_FILE, "r", encoding="utf-8") as f:
        CATEGORIES_META = json.load(f)
except FileNotFoundError:
    CATEGORIES_META = {}
    logger.warning("categories_meta.json не найден, создаём пустой.")

AVAILABLE_CATEGORIES = {}
for filename in os.listdir(WORDS_DIR):
    if filename.endswith(".json"):
        cat_key = filename[:-5]
        if cat_key in CATEGORIES_META:
            AVAILABLE_CATEGORIES[cat_key] = CATEGORIES_META[cat_key]
        else:
            AVAILABLE_CATEGORIES[cat_key] = {
                "label": cat_key.capitalize(),
                "instruction": "Переведите слово."
            }

logger.info(f"Доступные категории: {list(AVAILABLE_CATEGORIES.keys())}")

# ---------- FSM ----------
class WordsState(StatesGroup):
    category_chosen = State()

# ---------- Сессии ----------
user_sessions = {}

# ---------- Клавиатуры ----------
def get_categories_keyboard():
    top_order = ["gold_3000", "expert", "beginner"]
    rest_order = ["nouns", "verbs", "prepositions", "adverbs", "adjectives", 
                  "conjunctions", "false_friends", "phrasal_verbs", "irregular_verbs"]
    order = top_order + rest_order
    items = []
    for key in order:
        if key in AVAILABLE_CATEGORIES:
            label = AVAILABLE_CATEGORIES[key]["label"]
            items.append((label, f"word_cat_{key}"))
    items.append(("🔙 Назад", "back_to_main"))
    keyboard = []
    for i in range(0, len(items), 2):
        row = []
        text1, callback1 = items[i]
        row.append(InlineKeyboardButton(text=text1, callback_data=callback1))
        if i + 1 < len(items):
            text2, callback2 = items[i + 1]
            row.append(InlineKeyboardButton(text=text2, callback_data=callback2))
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_progress_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="word_revision")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="word_reset")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data="word_show_answer"),
            InlineKeyboardButton(text="Завершить", callback_data="word_finish")
        ]
    ])

def get_reset_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Да, сбросить", callback_data="word_confirm_reset")],
        [InlineKeyboardButton(text="Назад", callback_data="word_cancel_reset")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_clear_errors_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Да, сбросить ошибки", callback_data="word_confirm_clear_errors")],
        [InlineKeyboardButton(text="Назад", callback_data="word_cancel_clear_errors")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_finish_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="К категориям", callback_data="back_to_categories")]
    ])

# ---------- Вспомогательные ----------
def normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip().lower())

def is_correct(user_answer: str, correct_answer) -> bool:
    if isinstance(correct_answer, list):
        return normalize_text(user_answer) in [normalize_text(str(a)) for a in correct_answer]
    return normalize_text(user_answer) == normalize_text(str(correct_answer))

def load_words(category_key: str):
    file_path = os.path.join(WORDS_DIR, f"{category_key}.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def make_type_key(category_key: str) -> str:
    return f"words_{category_key}"

async def get_word_stats(user_id: int, category_key: str):
    type_key = make_type_key(category_key)
    return await get_user_stats_db(user_id, type_key, "beginner")

async def update_word_stats(user_id: int, category_key: str, correct: bool):
    type_key = make_type_key(category_key)
    await update_user_stats_db(user_id, type_key, "beginner", correct)

async def reset_word_stats(user_id: int, category_key: str):
    type_key = make_type_key(category_key)
    await reset_user_stats_db(user_id, type_key, "beginner")

async def add_word_error(user_id: int, category_key: str, word_index: int):
    type_key = make_type_key(category_key)
    await add_reading_error_db(user_id, type_key, "beginner", word_index)

async def remove_word_error(user_id: int, category_key: str, word_index: int):
    type_key = make_type_key(category_key)
    await remove_reading_error_db(user_id, type_key, "beginner", word_index)

async def get_word_errors(user_id: int, category_key: str):
    type_key = make_type_key(category_key)
    return await get_reading_errors_db(user_id, type_key, "beginner")

async def clear_word_errors(user_id: int, category_key: str):
    type_key = make_type_key(category_key)
    await clear_reading_errors_db(user_id, type_key, "beginner")

async def reset_word_progress(user_id: int, category_key: str):
    type_key = make_type_key(category_key)
    await reset_progress_index(user_id, type_key, "beginner")
    await reset_word_stats(user_id, category_key)
    await clear_word_errors(user_id, category_key)

# ---------- Отправка сообщений ----------
async def send_or_update_progress(
    bot: Bot,
    chat_id: int,
    user_id: int,
    category_key: str,
    instruction: str,
    msg_id: int = None,
    edit: bool = False
) -> int:
    label = AVAILABLE_CATEGORIES.get(category_key, {}).get("label", category_key)
    correct, _ = await get_word_stats(user_id, category_key)
    errors = await get_word_errors(user_id, category_key)
    text = f"<b>Режим:</b> {label}\n\n"
    text += f"{instruction}\n\n"
    text += f"<b>Ваш прогресс:</b>\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {len(errors)}"
    keyboard = get_progress_keyboard()
    if edit and msg_id:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return msg_id
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return sent.message_id

async def send_or_update_word_card(
    bot: Bot,
    chat_id: int,
    user_id: int,
    category_key: str,
    session: dict,
    msg_id: int = None,
    edit: bool = False
) -> int:
    words = session["words"]
    index = session["index"]
    if index >= len(words):
        index = 0
        session["index"] = 0
        type_key = make_type_key(category_key)
        await set_progress_index(user_id, type_key, "beginner", 0)
    word = words[index]
    session["current_word"] = word
    text = f"{word['word']}: _____"
    keyboard = get_task_keyboard()
    if edit and msg_id:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return msg_id
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return sent.message_id

# ---------- Вход в режим ----------
@router.callback_query(F.data == "start_words")
@router.message(Command("words"))
async def words_start(event, state: FSMContext):
    await state.clear()
    text = "✔️ Выберите категорию слов, которые хотите потренировать:"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=get_categories_keyboard())
    elif isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=get_categories_keyboard())
        await event.answer()

# ---------- Выбор категории ----------
@router.callback_query(F.data.startswith("word_cat_"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    category_key = callback.data.replace("word_cat_", "")

    try:
        words = load_words(category_key)
    except FileNotFoundError:
        logger.error(f"Файл для категории {category_key} не найден.")
        await callback.answer("Файл с этой категорией не найден.", show_alert=True)
        return
    except Exception as e:
        logger.error(f"Ошибка загрузки {category_key}: {e}")
        await callback.answer("Ошибка загрузки слов.", show_alert=True)
        return

    if not words:
        await callback.answer("В этой категории пока нет слов.", show_alert=True)
        return

    type_key = make_type_key(category_key)
    start_index = await get_progress_index(user_id, type_key, "beginner")
    if start_index >= len(words):
        start_index = 0
        await set_progress_index(user_id, type_key, "beginner", 0)

    session = {
        "words": words,
        "index": start_index,
        "correct": 0,
        "wrong": 0,
        "category": category_key,
        "current_word": None,
        "progress_msg_id": None,
        "card_msg_id": None
    }
    user_sessions[user_id] = session

    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    meta = AVAILABLE_CATEGORIES.get(category_key, {})
    instruction = meta.get("instruction", "Переведите слово.")
    try:
        progress_msg_id = await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            instruction,
            edit=False
        )
        session["progress_msg_id"] = progress_msg_id
    except Exception as e:
        logger.error(f"Ошибка отправки прогресса: {e}")
        await callback.message.answer("Ошибка при запуске режима. Попробуйте позже.")
        return

    try:
        card_msg_id = await send_or_update_word_card(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            session,
            edit=False
        )
        session["card_msg_id"] = card_msg_id
    except Exception as e:
        logger.error(f"Ошибка отправки карточки: {e}")
        await callback.message.answer("Ошибка при запуске режима. Попробуйте позже.")
        return

    await state.set_state(WordsState.category_chosen)
    logger.info(f"Состояние установлено для пользователя {user_id}: {await state.get_state()}")
    await callback.answer()

# ---------- Обработка ответов (только в состоянии category_chosen) ----------
@router.message(WordsState.category_chosen, F.text)
async def handle_answer(message: Message, state: FSMContext):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await message.answer("Пожалуйста, сначала выберите категорию через кнопку 'Words'.")
        return

    category_key = session["category"]
    words = session["words"]
    index = session.get("index", 0)
    if index >= len(words):
        index = 0
        type_key = make_type_key(category_key)
        await set_progress_index(user_id, type_key, "beginner", 0)
        session["index"] = 0
    current_word = words[index]
    session["current_word"] = current_word

    correct_answer = current_word["answer"]
    user_answer = message.text

    correct = is_correct(user_answer, correct_answer)
    if correct:
        session["correct"] += 1
        await update_word_stats(user_id, category_key, True)
        await remove_word_error(user_id, category_key, index)
    else:
        session["wrong"] += 1
        await update_word_stats(user_id, category_key, False)
        await add_word_error(user_id, category_key, index)

    example = current_word.get("example")
    if correct:
        result_text = f"Правильно! Правильный ответ: {correct_answer}"
    else:
        result_text = f"Неправильно. Правильный ответ: {correct_answer}"
    if example:
        result_text += f"\n\n<i>{example}</i>"
    await message.answer(result_text, parse_mode="HTML")

    session["index"] = (index + 1) % len(words)
    type_key = make_type_key(category_key)
    await set_progress_index(user_id, type_key, "beginner", session["index"])

    try:
        progress_msg_id = session.get("progress_msg_id")
        await send_or_update_progress(
            message.bot,
            message.chat.id,
            user_id,
            category_key,
            AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Переведите слово."),
            msg_id=progress_msg_id,
            edit=True
        )
        card_msg_id = session.get("card_msg_id")
        new_card_msg_id = await send_or_update_word_card(
            message.bot,
            message.chat.id,
            user_id,
            category_key,
            session,
            msg_id=card_msg_id,
            edit=True
        )
        session["card_msg_id"] = new_card_msg_id
    except Exception as e:
        logger.error(f"Ошибка обновления сообщений: {e}")

# ---------- Показать ответ (только в состоянии) ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_show_answer")
async def show_answer(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.answer("Сессия не найдена. Выберите категорию заново.", show_alert=True)
        return

    category_key = session["category"]
    words = session["words"]
    index = session.get("index", 0)
    if index >= len(words):
        index = 0
        type_key = make_type_key(category_key)
        await set_progress_index(user_id, type_key, "beginner", 0)
        session["index"] = 0
    current_word = words[index]
    session["current_word"] = current_word

    correct_answer = current_word["answer"]
    example = current_word.get("example")
    text = f"Правильный ответ: {correct_answer}"
    if example:
        text += f"\n\n<i>{example}</i>"
    await callback.message.answer(text, parse_mode="HTML")

    session["index"] = (index + 1) % len(words)
    type_key = make_type_key(category_key)
    await set_progress_index(user_id, type_key, "beginner", session["index"])

    try:
        progress_msg_id = session.get("progress_msg_id")
        await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Переведите слово."),
            msg_id=progress_msg_id,
            edit=True
        )
        card_msg_id = session.get("card_msg_id")
        new_card_msg_id = await send_or_update_word_card(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            session,
            msg_id=card_msg_id,
            edit=True
        )
        session["card_msg_id"] = new_card_msg_id
    except Exception as e:
        logger.error(f"Ошибка обновления сообщений: {e}")
    await callback.answer()

# ---------- Завершение сессии (только в состоянии) ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_finish")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.pop(user_id, None)
    if not session:
        await callback.answer("Сессия уже завершена.", show_alert=True)
        return

    category_key = session["category"]
    correct = session.get("correct", 0)
    wrong = session.get("wrong", 0)
    total = correct + wrong

    errors = await get_word_errors(user_id, category_key)
    remaining_errors = len(errors)

    if total == 0 and remaining_errors == 0:
        stats_text = "Вы не дали ни одного ответа."
    else:
        stats_text = f"✔️ Правильно: {correct}\n✖️ Ошибок: {wrong}\n"
        if total > 0:
            stats_text += f"Точность: {correct/total*100:.1f}%\n"
        if remaining_errors > 0:
            stats_text += f"Осталось ошибок: {remaining_errors}\n"
        else:
            stats_text += "Все ошибки исправлены! 🎉"

    await callback.message.edit_text(
        f"Сессия завершена!\n\n{stats_text}",
        reply_markup=get_finish_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()

# ---------- Работа над ошибками ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_revision")
async def word_revision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.message.answer("Сначала выберите категорию.")
        return

    category_key = session["category"]
    errors = await get_word_errors(user_id, category_key)
    if not errors:
        await callback.message.answer("🎉 Ошибок нет! Отличная работа.")
        return

    words = session["words"]
    error_words = [words[i] for i in errors if i < len(words)]
    if not error_words:
        await callback.message.answer("Ошибочные слова не найдены.")
        return

    session["revision_words"] = error_words
    session["revision_index"] = 0
    session["revision_mode"] = True
    await show_revision_word(callback.message, user_id, session, edit=False)

async def show_revision_word(message: Message, user_id: int, session: dict, edit: bool = False):
    error_words = session.get("revision_words", [])
    idx = session.get("revision_index", 0)
    if idx >= len(error_words):
        await message.answer("🎉 Вы просмотрели все ошибочные слова! Возвращаемся в учебный режим.")
        session["revision_mode"] = False
        session.pop("revision_words", None)
        session.pop("revision_index", None)
        category_key = session["category"]
        try:
            await send_or_update_progress(
                message.bot,
                message.chat.id,
                user_id,
                category_key,
                AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Переведите слово."),
                msg_id=session.get("progress_msg_id"),
                edit=True
            )
            card_msg_id = session.get("card_msg_id")
            new_card_msg_id = await send_or_update_word_card(
                message.bot,
                message.chat.id,
                user_id,
                category_key,
                session,
                msg_id=card_msg_id,
                edit=True
            )
            session["card_msg_id"] = new_card_msg_id
        except Exception as e:
            logger.error(f"Ошибка обновления сообщений: {e}")
        return

    word = error_words[idx]
    session["current_word"] = word
    text = f"🔴 Работа над ошибками\n\n{word['word']}: _____"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать ответ", callback_data="word_revision_show_answer")],
        [InlineKeyboardButton(text="Завершить работу над ошибками", callback_data="word_revision_finish")]
    ])
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        sent = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        session["revision_msg_id"] = sent.message_id

@router.callback_query(WordsState.category_chosen, F.data == "word_revision_show_answer")
async def revision_show_answer(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session or not session.get("revision_mode"):
        await callback.answer("Режим работы над ошибками не активен.")
        return
    error_words = session.get("revision_words", [])
    idx = session.get("revision_index", 0)
    if idx >= len(error_words):
        await callback.answer("Нет слов для показа.")
        return
    word = error_words[idx]
    correct_answer = word["answer"]
    example = word.get("example")
    text = f"Правильный ответ: {correct_answer}"
    if example:
        text += f"\n\n<i>{example}</i>"
    await callback.message.answer(text, parse_mode="HTML")
    session["revision_index"] = idx + 1
    await show_revision_word(callback.message, user_id, session, edit=True)
    await callback.answer()

@router.callback_query(WordsState.category_chosen, F.data == "word_revision_finish")
async def revision_finish(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if session:
        session["revision_mode"] = False
        session.pop("revision_words", None)
        session.pop("revision_index", None)
        await callback.message.answer("Возвращаемся в учебный режим.")
        category_key = session["category"]
        try:
            await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                category_key,
                AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Переведите слово."),
                msg_id=session.get("progress_msg_id"),
                edit=True
            )
            card_msg_id = session.get("card_msg_id")
            new_card_msg_id = await send_or_update_word_card(
                callback.bot,
                callback.message.chat.id,
                user_id,
                category_key,
                session,
                msg_id=card_msg_id,
                edit=True
            )
            session["card_msg_id"] = new_card_msg_id
        except Exception as e:
            logger.error(f"Ошибка обновления сообщений: {e}")
    await callback.answer()

# ---------- Сброс прогресса ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_reset")
async def word_reset_confirm(callback: CallbackQuery):
    await callback.answer()
    confirm_text = (
        "Вы уверены, что хотите сбросить весь прогресс для этой категории?\n"
        "Статистика, ошибки и текущее слово будут обнулены.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(confirm_text, reply_markup=get_reset_confirmation_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "word_confirm_reset")
async def word_confirm_reset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.message.answer("Сессия не найдена.")
        return
    category_key = session["category"]
    await reset_word_progress(user_id, category_key)
    session["index"] = 0
    session["correct"] = 0
    session["wrong"] = 0
    type_key = make_type_key(category_key)
    await set_progress_index(user_id, type_key, "beginner", 0)
    await callback.message.edit_text("Прогресс сброшен. Начинаем с первого слова.")
    try:
        await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Переведите слово."),
            msg_id=session.get("progress_msg_id"),
            edit=True
        )
        card_msg_id = session.get("card_msg_id")
        new_card_msg_id = await send_or_update_word_card(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            session,
            msg_id=card_msg_id,
            edit=True
        )
        session["card_msg_id"] = new_card_msg_id
    except Exception as e:
        logger.error(f"Ошибка обновления сообщений: {e}")
    try:
        await callback.message.delete()
    except Exception:
        pass

@router.callback_query(WordsState.category_chosen, F.data == "word_cancel_reset")
async def word_cancel_reset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if session:
        try:
            await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                session["category"],
                AVAILABLE_CATEGORIES.get(session["category"], {}).get("instruction", "Переведите слово."),
                msg_id=session.get("progress_msg_id"),
                edit=True
            )
            card_msg_id = session.get("card_msg_id")
            new_card_msg_id = await send_or_update_word_card(
                callback.bot,
                callback.message.chat.id,
                user_id,
                session["category"],
                session,
                msg_id=card_msg_id,
                edit=True
            )
            session["card_msg_id"] = new_card_msg_id
        except Exception as e:
            logger.error(f"Ошибка обновления сообщений: {e}")
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.message.edit_text("Выберите категорию:", reply_markup=get_categories_keyboard())

# ---------- К категориям ----------
@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user_sessions.pop(user_id, None)
    await callback.message.edit_text("✔️ Выберите категорию слов, которые хотите потренировать:", reply_markup=get_categories_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_sessions.pop(user_id, None)
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()