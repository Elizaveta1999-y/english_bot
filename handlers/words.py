import os
import json
import re
import logging
import random
import hashlib
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.db import (
    get_user_stats_db, update_user_stats_db, reset_user_stats_db,
    add_reading_error_db, remove_reading_error_db, get_reading_errors_db, clear_reading_errors_db,
    get_progress_index, set_progress_index, reset_progress_index,
    get_random_order, set_random_order,
    get_order_hash, set_order_hash,
    get_connection,
)

logger = logging.getLogger(__name__)
router = Router()

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
        if cat_key == "irregular_verbs":
            continue
        if cat_key in CATEGORIES_META:
            AVAILABLE_CATEGORIES[cat_key] = CATEGORIES_META[cat_key]
        else:
            AVAILABLE_CATEGORIES[cat_key] = {
                "label": cat_key.capitalize(),
                "instruction": "Напишите перевод на английский."
            }

logger.info(f"Доступные категории: {list(AVAILABLE_CATEGORIES.keys())}")

class WordsState(StatesGroup):
    category_chosen = State()

user_sessions = {}
user_message_ids = {}

# ---------- Клавиатуры ----------
def get_categories_keyboard():
    left_col = ["gold_3000", "beginner", "expert", "verbs", "adverbs"]
    right_col = ["nouns", "adjectives", "prepositions", "conjunctions", "false_friends"]
    keyboard = []
    for i in range(len(left_col)):
        left_key = left_col[i]
        right_key = right_col[i]
        row = []
        if left_key in AVAILABLE_CATEGORIES:
            row.append(InlineKeyboardButton(
                text=AVAILABLE_CATEGORIES[left_key]["label"],
                callback_data=f"word_cat_{left_key}"
            ))
        if right_key in AVAILABLE_CATEGORIES:
            row.append(InlineKeyboardButton(
                text=AVAILABLE_CATEGORIES[right_key]["label"],
                callback_data=f"word_cat_{right_key}"
            ))
        if row:
            keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_progress_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="word_revision")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="word_reset")]
    ])

def get_task_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data="word_show_answer"),
            InlineKeyboardButton(text="Завершить", callback_data="word_finish")
        ]
    ])

def get_reset_confirmation_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить", callback_data="word_confirm_reset")],
        [InlineKeyboardButton(text="Назад", callback_data="word_cancel_reset")]
    ])

def get_revision_info_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Учебный режим", callback_data="word_revision_back_to_study")],
        [InlineKeyboardButton(text="Сбросить ошибки", callback_data="word_reset_errors")]
    ])

def get_reset_errors_confirmation_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить ошибки", callback_data="word_confirm_reset_errors")],
        [InlineKeyboardButton(text="Назад", callback_data="word_cancel_reset_errors")]
    ])

# ---------- Вспомогательные ----------
def normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip().lower())

def split_answers(answer_str: str) -> list:
    if isinstance(answer_str, list):
        return answer_str
    if '/' in answer_str or ',' in answer_str:
        parts = re.split(r'[\/,]\s*', answer_str)
        return [p.strip() for p in parts if p.strip()]
    return [answer_str]

def is_correct(user_answer: str, correct_answer) -> bool:
    user_ans = normalize_text(user_answer)
    if isinstance(correct_answer, str):
        variants = split_answers(correct_answer)
    else:
        variants = [normalize_text(str(v)) for v in correct_answer]
    return user_ans in variants

def load_words(category_key: str):
    file_path = os.path.join(WORDS_DIR, f"{category_key}.json")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON в файле {file_path}: {e}")
        raise ValueError(f"Ошибка в файле {category_key}.json: {e}")

def make_type_key(category_key: str) -> str:
    return f"words_{category_key}"

async def get_word_stats(user_id: int, category_key: str):
    return await get_user_stats_db(user_id, make_type_key(category_key), "beginner")

async def update_word_stats(user_id: int, category_key: str, correct: bool):
    await update_user_stats_db(user_id, make_type_key(category_key), "beginner", correct)

async def reset_word_stats(user_id: int, category_key: str):
    await reset_user_stats_db(user_id, make_type_key(category_key), "beginner")

async def add_word_error(user_id: int, category_key: str, word_index: int):
    await add_reading_error_db(user_id, make_type_key(category_key), "beginner", word_index)

async def remove_word_error(user_id: int, category_key: str, word_index: int):
    await remove_reading_error_db(user_id, make_type_key(category_key), "beginner", word_index)

async def get_word_errors(user_id: int, category_key: str):
    return await get_reading_errors_db(user_id, make_type_key(category_key), "beginner")

async def clear_word_errors(user_id: int, category_key: str):
    await clear_reading_errors_db(user_id, make_type_key(category_key), "beginner")

async def reset_word_progress(user_id: int, category_key: str):
    await reset_progress_index(user_id, make_type_key(category_key), "beginner")
    await reset_word_stats(user_id, category_key)
    await clear_word_errors(user_id, category_key)

# ---------- Убираем кнопки ----------
async def remove_buttons_from_messages(bot: Bot, chat_id: int, message_ids: list):
    if not message_ids:
        return
    logger.info(f"Убираем кнопки у сообщений: {message_ids}")
    for msg_id in message_ids:
        if msg_id:
            try:
                await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
                logger.debug(f"Кнопки убраны у сообщения {msg_id}")
            except Exception as e:
                error_text = str(e).lower()
                if "message is not modified" in error_text:
                    logger.debug(f"Сообщение {msg_id} уже без кнопок, пропускаем")
                else:
                    logger.warning(f"Не удалось убрать кнопки у {msg_id}: {e}")

async def cleanup_practice(user_id: int, bot: Bot, chat_id: int, send_message: bool = True):
    logger.info(f"Очистка практики для user_id={user_id}, send_message={send_message}")
    if user_id in user_message_ids:
        msg_ids = list(user_message_ids[user_id].values())
        logger.info(f"Найдены ID сообщений для очистки: {msg_ids}")
        await remove_buttons_from_messages(bot, chat_id, msg_ids)
    else:
        logger.warning(f"Нет сообщений для очистки для user_id={user_id}")
    session = user_sessions.pop(user_id, None)
    if session:
        logger.info(f"Сессия для user_id={user_id} удалена")
    else:
        logger.warning(f"Сессия для user_id={user_id} не найдена при очистке")
    if send_message:
        await bot.send_message(chat_id, "Практика завершена.")

# ---------- Отправка/обновление прогресса ----------
async def send_or_update_progress(
    bot: Bot,
    chat_id: int,
    user_id: int,
    category_key: str,
    instruction: str,
    msg_id: int = None,
    edit: bool = False,
    force_buttons: bool = True
) -> int:
    label = AVAILABLE_CATEGORIES.get(category_key, {}).get("label", category_key)
    correct, _ = await get_word_stats(user_id, category_key)
    errors = await get_word_errors(user_id, category_key)
    text = f"<b>Режим:</b> {label}\n\n"
    text += f"{instruction}\n\n"
    text += f"<b>Ваш прогресс:</b>\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {len(errors)}"
    keyboard = get_progress_keyboard() if force_buttons else None

    if edit and msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.debug(f"Прогресс обновлён (редактирование) msg_id={msg_id}")
            return msg_id
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                logger.debug(f"Прогресс не изменился, пропускаем редактирование msg_id={msg_id}")
                return msg_id
            else:
                logger.warning(f"Не удалось отредактировать прогресс msg_id={msg_id}, отправляем новое: {e}")
                sent = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
                if user_id not in user_message_ids:
                    user_message_ids[user_id] = {}
                user_message_ids[user_id]["progress"] = sent.message_id
                return sent.message_id
    else:
        sent = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
        if user_id not in user_message_ids:
            user_message_ids[user_id] = {}
        user_message_ids[user_id]["progress"] = sent.message_id
        return sent.message_id

async def send_new_word_card(
    bot: Bot,
    chat_id: int,
    user_id: int,
    category_key: str,
    session: dict,
    old_msg_id: int = None,
    is_revision: bool = False
) -> int:
    if old_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=old_msg_id, reply_markup=None)
            logger.debug(f"Кнопки убраны у старой карточки {old_msg_id}")
        except Exception as e:
            error_text = str(e).lower()
            if "message is not modified" in error_text:
                logger.debug(f"Старая карточка {old_msg_id} уже без кнопок")
            else:
                logger.warning(f"Не удалось убрать кнопки у карточки {old_msg_id}: {e}")

    if is_revision:
        words = session.get("revision_words", [])
        index = session.get("revision_index", 0)
        if index >= len(words):
            index = 0
            session["revision_index"] = 0
        word = words[index]
    else:
        shuffled_order = session["shuffled_order"]
        index = session["index"]
        if index >= len(shuffled_order):
            index = 0
            session["index"] = 0
            await set_progress_index(user_id, make_type_key(category_key), "beginner", 0)
        word_idx = shuffled_order[index]
        word = session["words"][word_idx]

    session["current_word"] = word
    text = f"{word['word']}: _____"
    keyboard = get_task_keyboard()
    sent = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
    logger.debug(f"Отправлена новая карточка msg_id={sent.message_id}")
    if user_id not in user_message_ids:
        user_message_ids[user_id] = {}
    key = "revision_card" if is_revision else "card"
    user_message_ids[user_id][key] = sent.message_id
    return sent.message_id

# ---------- Обработчики ----------
@router.callback_query(F.data == "start_words")
@router.message(Command("words"))
async def words_start(event, state: FSMContext):
    logger.info("Вызван words_start")
    if isinstance(event, Message):
        user_id = event.from_user.id
        chat_id = event.chat.id
        bot = event.bot
        is_message = True
        try:
            await event.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение с командой: {e}")
    else:
        user_id = event.from_user.id
        chat_id = event.message.chat.id
        bot = event.bot
        is_message = False
        try:
            await event.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

    await cleanup_practice(user_id, bot, chat_id, send_message=False)
    await state.clear()
    if user_id not in user_message_ids:
        user_message_ids[user_id] = {}

    text = "✔️ Выберите категорию слов, которые хотите потренировать:"
    if is_message:
        sent = await event.answer(text, reply_markup=get_categories_keyboard())
        if sent:
            user_message_ids[user_id]["categories"] = sent.message_id
    else:
        sent = await bot.send_message(chat_id, text, reply_markup=get_categories_keyboard())
        user_message_ids[user_id]["categories"] = sent.message_id
        await event.answer()

@router.callback_query(F.data.startswith("word_cat_"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    category_key = callback.data.replace("word_cat_", "")
    logger.info(f"========== ВХОД В КАТЕГОРИЮ: {category_key} ==========")
    logger.info(f"user_id={user_id}")

    if user_id in user_message_ids and "categories" in user_message_ids[user_id]:
        del user_message_ids[user_id]["categories"]

    try:
        words = load_words(category_key)
        logger.info(f"Загружено слов из файла: {len(words)}")
    except FileNotFoundError:
        await callback.answer("Файл с этой категорией не найден.", show_alert=True)
        return
    except ValueError as e:
        await callback.answer(f"Ошибка в файле категории: {e}", show_alert=True)
        return
    except Exception as e:
        logger.error(f"Неизвестная ошибка загрузки {category_key}: {e}")
        await callback.answer("Ошибка загрузки слов.", show_alert=True)
        return

    if not words:
        await callback.answer("В этой категории пока нет слов.", show_alert=True)
        return

    level_key = make_type_key(category_key)
    logger.info(f"level_key={level_key}")

    # Вычисляем хеш
    content_str = json.dumps(words, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
    logger.info(f"Текущий хеш файла: {current_hash[:16]}...")

    # Получаем данные из БД
    saved_hash = await get_order_hash(user_id, level_key)
    shuffled_order = await get_random_order(user_id, level_key)
    logger.info(f"Сохранённый хеш: {saved_hash[:16] if saved_hash else 'None'}...")
    logger.info(f"Сохранённый порядок: {shuffled_order[:20] if shuffled_order else 'None'}...")
    logger.info(f"Длина порядка: {len(shuffled_order) if shuffled_order else 0}")

    # Проверки
    need_recreate = False
    reasons = []

    if saved_hash is None:
        reasons.append("Хеш отсутствует")
        need_recreate = True
    elif saved_hash != current_hash:
        reasons.append("Хеш не совпадает")
        need_recreate = True
    elif shuffled_order is None:
        reasons.append("Порядок отсутствует")
        need_recreate = True
    elif len(shuffled_order) != len(words):
        reasons.append(f"Длина не совпадает (БД={len(shuffled_order)}, файл={len(words)})")
        need_recreate = True
    elif any(idx >= len(words) for idx in shuffled_order):
        reasons.append("Есть невалидные индексы")
        need_recreate = True
    elif shuffled_order == list(range(len(words))):
        reasons.append("Порядок не перемешан")
        need_recreate = True

    if reasons:
        logger.info(f"Причины пересоздания: {', '.join(reasons)}")
    else:
        logger.info("Все проверки пройдены, порядок валидный")

    if need_recreate:
        logger.info(f"!!! ПЕРЕСОЗДАЁМ ПОРЯДОК для {category_key} !!!")
        conn = await get_connection()
        await conn.execute("DELETE FROM random_order WHERE user_id = $1 AND level_key = $2", user_id, level_key)
        await conn.close()
        logger.info("Старая запись удалена")

        new_order = list(range(len(words)))
        random.shuffle(new_order)
        shuffled_order = new_order
        logger.info(f"Новый порядок: {shuffled_order[:30]}...")

        await set_random_order(user_id, level_key, shuffled_order)
        await set_order_hash(user_id, level_key, current_hash)
        await reset_progress_index(user_id, level_key, "beginner")
        start_index = 0
        logger.info("Новый порядок сохранён, хеш обновлён, индекс сброшен на 0")
    else:
        start_index = await get_progress_index(user_id, level_key, "beginner")
        if start_index >= len(shuffled_order):
            start_index = 0
            await set_progress_index(user_id, level_key, "beginner", 0)
        logger.info(f"Используем существующий порядок, индекс={start_index}")

    session = {
        "words": words,
        "shuffled_order": shuffled_order,
        "index": start_index,
        "correct": 0,
        "wrong": 0,
        "category": category_key,
        "current_word": None,
        "progress_msg_id": None,
        "card_msg_id": None,
        "revision_mode": False,
        "revision_words": None,
        "revision_index": 0,
        "revision_info_msg_id": None,
        "revision_card_msg_id": None,
        "revision_corrected": 0,
        "revision_total": 0,
        "revision_initial_errors": [],
    }
    user_sessions[user_id] = session

    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    meta = AVAILABLE_CATEGORIES.get(category_key, {})
    instruction = meta.get("instruction", "Напишите перевод на английский.")

    try:
        progress_msg_id = await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            instruction,
            edit=False,
            force_buttons=True
        )
        session["progress_msg_id"] = progress_msg_id
        logger.info(f"Создано сообщение прогресса msg_id={progress_msg_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки прогресса: {e}")
        await callback.message.answer("Ошибка при запуске режима.")
        return

    try:
        card_msg_id = await send_new_word_card(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            session,
            old_msg_id=None,
            is_revision=False
        )
        session["card_msg_id"] = card_msg_id
        logger.info(f"Создана карточка msg_id={card_msg_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки карточки: {e}")
        await callback.message.answer("Ошибка при запуске режима.")
        return

    await state.set_state(WordsState.category_chosen)
    await callback.answer()

@router.message(WordsState.category_chosen, F.text)
async def handle_answer(message: Message, state: FSMContext):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await message.answer("Пожалуйста, сначала выберите категорию через кнопку 'Words'.")
        return

    if message.text.startswith("/"):
        await cleanup_practice(user_id, message.bot, message.chat.id, send_message=True)
        command = message.text.split()[0].lower()
        if command == "/words":
            await words_start(message, state)
        elif command == "/start":
            from .start import show_main_menu
            await show_main_menu(message, edit=False)
        else:
            await message.answer("Практика завершена.")
        return

    if session.get("revision_mode"):
        await handle_revision_answer(message, session, state)
        return

    category_key = session["category"]
    shuffled_order = session["shuffled_order"]
    index = session.get("index", 0)
    if index >= len(shuffled_order):
        index = 0
        await set_progress_index(user_id, make_type_key(category_key), "beginner", 0)
        session["index"] = 0
    word_idx = shuffled_order[index]
    current_word = session["words"][word_idx]
    session["current_word"] = current_word

    correct_answer = current_word["answer"]
    user_answer = message.text

    correct = is_correct(user_answer, correct_answer)

    if correct:
        await remove_word_error(user_id, category_key, word_idx)
        await update_word_stats(user_id, category_key, True)
        session["correct"] += 1

        example = current_word.get("example")
        result_text = "Правильно!"
        if example:
            result_text += f"\n\n<i>{example}</i>"
        await message.answer(result_text, parse_mode="HTML")
    else:
        await update_word_stats(user_id, category_key, False)
        await add_word_error(user_id, category_key, word_idx)
        session["wrong"] += 1

        example = current_word.get("example")
        result_text = f"Неправильно. Правильный ответ: {correct_answer}"
        if example:
            result_text += f"\n\n<i>{example}</i>"
        await message.answer(result_text, parse_mode="HTML")

    session["index"] = (index + 1) % len(shuffled_order)
    await set_progress_index(user_id, make_type_key(category_key), "beginner", session["index"])

    try:
        progress_msg_id = session.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            message.bot,
            message.chat.id,
            user_id,
            category_key,
            AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Напишите перевод на английский."),
            msg_id=progress_msg_id,
            edit=True,
            force_buttons=True
        )
        if new_progress_id != progress_msg_id:
            session["progress_msg_id"] = new_progress_id
            logger.info(f"Обновлён progress_msg_id на {new_progress_id}")
    except Exception as e:
        logger.error(f"Ошибка обновления прогресса: {e}")

    try:
        old_card_id = session.get("card_msg_id")
        new_card_id = await send_new_word_card(
            message.bot,
            message.chat.id,
            user_id,
            category_key,
            session,
            old_msg_id=old_card_id,
            is_revision=False
        )
        session["card_msg_id"] = new_card_id
    except Exception as e:
        logger.error(f"Ошибка отправки новой карточки: {e}")

# ---------- Режим работы над ошибками ----------
async def handle_revision_answer(message: Message, session: dict, state: FSMContext):
    user_id = message.from_user.id
    category_key = session["category"]
    error_words = session.get("revision_words", [])
    idx = session.get("revision_index", 0)

    if idx >= len(error_words):
        corrected = session.get("revision_corrected", 0)
        total = session.get("revision_total", len(error_words))
        remaining = total - corrected

        if remaining == 0:
            await message.answer("🎉 Вы исправили все ошибки!")
        else:
            if corrected == 0:
                await message.answer("Вы не исправили ни одной ошибки.")
            else:
                await message.answer(
                    f"Вы исправили {corrected} из {total} ошибок. Осталось ошибок: {remaining}"
                )
        await exit_revision(message, session)
        return

    current_word = error_words[idx]
    session["current_word"] = current_word
    correct_answer = current_word["answer"]
    user_answer = message.text

    correct = is_correct(user_answer, correct_answer)

    # Находим реальный индекс слова в основном списке (по объекту)
    main_index = session["words"].index(current_word)

    if correct:
        await remove_word_error(user_id, category_key, main_index)
        await update_word_stats(user_id, category_key, True)
        session["revision_corrected"] = session.get("revision_corrected", 0) + 1
        await message.answer(f"Правильно! Ответ: {correct_answer}")
    else:
        # Неправильно – ошибка остаётся, статистика НЕ меняется
        await message.answer(f"Неправильно. Правильный ответ: {correct_answer}")

    session["revision_index"] = idx + 1
    if session["revision_index"] < len(error_words):
        # Убираем кнопки у предыдущей карточки (если есть)
        old_card_id = session.get("revision_card_msg_id")
        if old_card_id:
            try:
                await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=old_card_id, reply_markup=None)
            except Exception as e:
                logger.warning(f"Не удалось убрать кнопки у старой карточки ревизии: {e}")

        # Отправляем новое сообщение со следующим словом
        next_word = error_words[session["revision_index"]]
        text = f"{next_word['word']}: _____"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Показать ответ", callback_data="word_revision_show_answer"),
             InlineKeyboardButton(text="Завершить", callback_data="word_revision_finish")]
        ])
        sent = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        session["revision_card_msg_id"] = sent.message_id
        if user_id not in user_message_ids:
            user_message_ids[user_id] = {}
        user_message_ids[user_id]["revision_card"] = sent.message_id
    else:
        await finish_revision(message, session)

async def finish_revision(message: Message, session: dict):
    corrected = session.get("revision_corrected", 0)
    total = session.get("revision_total", 0)
    remaining = total - corrected

    if remaining == 0:
        await message.answer("🎉 Вы исправили все ошибки!")
    else:
        if corrected == 0:
            await message.answer("Вы не исправили ни одной ошибки.")
        else:
            await message.answer(
                f"Вы исправили {corrected} из {total} ошибок. Осталось ошибок: {remaining}"
            )
    await exit_revision(message, session)

async def exit_revision(message: Message, session: dict):
    session["revision_mode"] = False
    # Убираем кнопки у последней карточки ревизии, если она есть
    if session.get("revision_card_msg_id"):
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=session["revision_card_msg_id"], reply_markup=None)
        except Exception:
            pass
    # Убираем кнопки у информационного сообщения
    if session.get("revision_info_msg_id"):
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=session["revision_info_msg_id"], reply_markup=None)
        except Exception:
            pass
    
    session.pop("revision_info_msg_id", None)
    session.pop("revision_card_msg_id", None)
    session.pop("revision_words", None)
    session.pop("revision_index", None)
    session.pop("revision_corrected", None)
    session.pop("revision_total", None)
    session.pop("revision_initial_errors", None)

    category_key = session["category"]
    user_id = message.from_user.id
    try:
        progress_msg_id = session.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            message.bot,
            message.chat.id,
            user_id,
            category_key,
            AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Напишите перевод на английский."),
            msg_id=progress_msg_id,
            edit=True,
            force_buttons=True
        )
        if new_progress_id != progress_msg_id:
            session["progress_msg_id"] = new_progress_id
    except Exception as e:
        logger.error(f"Ошибка возврата кнопок прогресса: {e}")

    try:
        old_card_id = session.get("card_msg_id")
        new_card_id = await send_new_word_card(
            message.bot,
            message.chat.id,
            user_id,
            category_key,
            session,
            old_msg_id=old_card_id,
            is_revision=False
        )
        session["card_msg_id"] = new_card_id
    except Exception as e:
        logger.error(f"Ошибка отправки новой карточки: {e}")

# ---------- Показать ответ (обычный режим) ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_show_answer")
async def show_answer(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.answer("Сессия не найдена.", show_alert=True)
        return

    if session.get("revision_mode"):
        await revision_show_answer(callback, session)
        return

    category_key = session["category"]
    shuffled_order = session["shuffled_order"]
    index = session.get("index", 0)
    if index >= len(shuffled_order):
        index = 0
        await set_progress_index(user_id, make_type_key(category_key), "beginner", 0)
        session["index"] = 0
    word_idx = shuffled_order[index]
    current_word = session["words"][word_idx]
    session["current_word"] = current_word

    correct_answer = current_word["answer"]
    example = current_word.get("example")
    text = f"Правильный ответ: {correct_answer}"
    if example:
        text += f"\n\n<i>{example}</i>"
    await callback.message.answer(text, parse_mode="HTML")

    session["index"] = (index + 1) % len(shuffled_order)
    await set_progress_index(user_id, make_type_key(category_key), "beginner", session["index"])

    try:
        old_card_id = session.get("card_msg_id")
        new_card_id = await send_new_word_card(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            session,
            old_msg_id=old_card_id,
            is_revision=False
        )
        session["card_msg_id"] = new_card_id
    except Exception as e:
        logger.error(f"Ошибка отправки новой карточки: {e}")

    await callback.answer()

# ---------- Показать ответ в режиме ревизии ----------
async def revision_show_answer(callback: CallbackQuery, session: dict):
    error_words = session.get("revision_words", [])
    idx = session.get("revision_index", 0)
    if idx >= len(error_words):
        await callback.answer("Нет слов для показа.", show_alert=True)
        return

    word = error_words[idx]
    correct_answer = word["answer"]
    example = word.get("example")
    text = f"Правильный ответ: {correct_answer}"
    if example:
        text += f"\n\n<i>{example}</i>"
    await callback.message.answer(text, parse_mode="HTML")

    session["revision_index"] = idx + 1
    if session["revision_index"] < len(error_words):
        # Убираем кнопки у предыдущей карточки
        old_card_id = session.get("revision_card_msg_id")
        if old_card_id:
            try:
                await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=old_card_id, reply_markup=None)
            except Exception:
                pass

        # Отправляем новое сообщение со следующим словом
        next_word = error_words[session["revision_index"]]
        text = f"{next_word['word']}: _____"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Показать ответ", callback_data="word_revision_show_answer"),
             InlineKeyboardButton(text="Завершить", callback_data="word_revision_finish")]
        ])
        sent = await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        session["revision_card_msg_id"] = sent.message_id
        user_id = callback.from_user.id
        if user_id not in user_message_ids:
            user_message_ids[user_id] = {}
        user_message_ids[user_id]["revision_card"] = sent.message_id
    else:
        await finish_revision(callback.message, session)

    await callback.answer()

# ---------- Завершение сессии ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_finish")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.pop(user_id, None)
    if not session:
        await callback.answer("Сессия уже завершена.", show_alert=True)
        return

    correct = session.get("correct", 0)
    wrong = session.get("wrong", 0)
    total = correct + wrong

    if total == 0:
        header = "Сессия завершена 🙌🏻"
        stats_text = "Вы не ответили ни на одно задание."
    else:
        header = "Сессия завершена 🙌🏽"
        stats_text = f"✔️ Правильно: {correct}\n✖️ Ошибок: {wrong}"

    if user_id in user_message_ids:
        msg_ids = []
        if "progress" in user_message_ids[user_id]:
            msg_ids.append(user_message_ids[user_id]["progress"])
        if "card" in user_message_ids[user_id]:
            msg_ids.append(user_message_ids[user_id]["card"])
        await remove_buttons_from_messages(callback.bot, callback.message.chat.id, msg_ids)

    await callback.message.answer(
        f"{header}\n{stats_text}",
        parse_mode="HTML"
    )

    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=False)
    await callback.answer()

# ---------- Вход в работу над ошибками ----------
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

    initial_errors = errors.copy()
    session["revision_initial_errors"] = initial_errors

    words = session["words"]
    error_words = [words[i] for i in errors if i < len(words)]
    if not error_words:
        await callback.message.answer("Ошибочные слова не найдены.")
        return

    old_info_id = session.get("revision_info_msg_id")
    old_card_id = session.get("revision_card_msg_id")
    if old_info_id or old_card_id:
        old_ids = [old_info_id, old_card_id]
        await remove_buttons_from_messages(callback.bot, callback.message.chat.id, old_ids)
        session.pop("revision_info_msg_id", None)
        session.pop("revision_card_msg_id", None)

    if user_id in user_message_ids:
        msg_ids_to_remove = []
        if "progress" in user_message_ids[user_id]:
            msg_ids_to_remove.append(user_message_ids[user_id]["progress"])
        if "card" in user_message_ids[user_id]:
            msg_ids_to_remove.append(user_message_ids[user_id]["card"])
        if msg_ids_to_remove:
            await remove_buttons_from_messages(callback.bot, callback.message.chat.id, msg_ids_to_remove)

    label = AVAILABLE_CATEGORIES.get(category_key, {}).get("label", category_key)
    text = f"<b>Работа над ошибками</b>\n"
    text += f"Категория: {label}\n\n"
    text += f"Слов на повторение: {len(error_words)}"

    sent_info = await callback.message.answer(
        text,
        reply_markup=get_revision_info_keyboard(),
        parse_mode="HTML"
    )
    session["revision_info_msg_id"] = sent_info.message_id
    if user_id not in user_message_ids:
        user_message_ids[user_id] = {}
    user_message_ids[user_id]["revision_info"] = sent_info.message_id

    session["revision_words"] = error_words
    session["revision_index"] = 0
    session["revision_mode"] = True
    session["revision_corrected"] = 0
    session["revision_total"] = len(error_words)

    first_word = error_words[0]
    text_card = f"{first_word['word']}: _____"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать ответ", callback_data="word_revision_show_answer"),
         InlineKeyboardButton(text="Завершить", callback_data="word_revision_finish")]
    ])
    sent_card = await callback.message.answer(text_card, reply_markup=keyboard, parse_mode="HTML")
    session["revision_card_msg_id"] = sent_card.message_id
    user_message_ids[user_id]["revision_card"] = sent_card.message_id

@router.callback_query(WordsState.category_chosen, F.data == "word_revision_show_answer")
async def revision_show_answer_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session or not session.get("revision_mode"):
        await callback.answer("Режим работы над ошибками не активен.", show_alert=True)
        return
    await revision_show_answer(callback, session)

@router.callback_query(WordsState.category_chosen, F.data == "word_revision_finish")
async def revision_finish_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.answer("Сессия не найдена.", show_alert=True)
        return
    await finish_revision(callback.message, session)
    await callback.answer()

@router.callback_query(WordsState.category_chosen, F.data == "word_revision_back_to_study")
async def revision_back_to_study(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.answer("Сессия не найдена.")
        return
    await exit_revision(callback.message, session)
    await callback.answer()

# ---------- Сбросить ошибки ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_reset_errors")
async def reset_errors(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.message.answer("Сессия не найдена.")
        return

    confirm_text = (
        "Вы уверены, что хотите сбросить все ошибки для этой категории?\n"
        "Ошибки будут удалены, вы продолжите с места на котором остановились.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(
        confirm_text,
        reply_markup=get_reset_errors_confirmation_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "word_confirm_reset_errors")
async def confirm_reset_errors(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.message.answer("Сессия не найдена.")
        return

    category_key = session["category"]
    await clear_word_errors(user_id, category_key)

    try:
        await callback.message.edit_text("Ошибки сброшены.", reply_markup=None)
    except Exception:
        pass

    await exit_revision(callback.message, session)

@router.callback_query(F.data == "word_cancel_reset_errors")
async def cancel_reset_errors(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.message.answer("Сессия не найдена.")
        return

    info_msg_id = session.get("revision_info_msg_id")
    if info_msg_id:
        label = AVAILABLE_CATEGORIES.get(session["category"], {}).get("label", session["category"])
        errors = await get_word_errors(user_id, session["category"])
        text = f"<b>Работа над ошибками</b>\n"
        text += f"Категория: {label}\n\n"
        text += f"Слов на повторение: {len(errors)}"
        try:
            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=info_msg_id,
                text=text,
                reply_markup=get_revision_info_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            pass
    try:
        await callback.message.delete()
    except Exception:
        pass

# ---------- Сброс прогресса ----------
@router.callback_query(WordsState.category_chosen, F.data == "word_reset")
async def word_reset_confirm(callback: CallbackQuery):
    await callback.answer()
    confirm_text = (
        "Вы уверены, что хотите сбросить весь прогресс для этой категории?\n"
        "Статистика, ошибки и текущее задание будут обнулены.\n\n"
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

    words = session["words"]
    new_order = list(range(len(words)))
    random.shuffle(new_order)
    level_key = make_type_key(category_key)

    conn = await get_connection()
    await conn.execute("DELETE FROM random_order WHERE user_id = $1 AND level_key = $2", user_id, level_key)
    await conn.close()

    await set_random_order(user_id, level_key, new_order)
    content_str = json.dumps(words, sort_keys=True, ensure_ascii=False)
    new_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
    await set_order_hash(user_id, level_key, new_hash)
    session["shuffled_order"] = new_order
    session["index"] = 0
    session["correct"] = 0
    session["wrong"] = 0
    await set_progress_index(user_id, make_type_key(category_key), "beginner", 0)

    try:
        await callback.message.edit_text(
            "Прогресс сброшен. Задания перемешаны заново, вы начнёте с первого.",
            reply_markup=None
        )
    except Exception:
        pass

    try:
        progress_msg_id = session.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            AVAILABLE_CATEGORIES.get(category_key, {}).get("instruction", "Напишите перевод на английский."),
            msg_id=progress_msg_id,
            edit=True,
            force_buttons=True
        )
        if new_progress_id != progress_msg_id:
            session["progress_msg_id"] = new_progress_id
        old_card_id = session.get("card_msg_id")
        new_card_id = await send_new_word_card(
            callback.bot,
            callback.message.chat.id,
            user_id,
            category_key,
            session,
            old_msg_id=old_card_id,
            is_revision=False
        )
        session["card_msg_id"] = new_card_id
    except Exception as e:
        logger.error(f"Ошибка обновления после сброса: {e}")

@router.callback_query(WordsState.category_chosen, F.data == "word_cancel_reset")
async def word_cancel_reset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if session:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            progress_msg_id = session.get("progress_msg_id")
            new_progress_id = await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                session["category"],
                AVAILABLE_CATEGORIES.get(session["category"], {}).get("instruction", "Напишите перевод на английский."),
                msg_id=progress_msg_id,
                edit=True,
                force_buttons=True
            )
            if new_progress_id != progress_msg_id:
                session["progress_msg_id"] = new_progress_id
        except Exception as e:
            logger.error(f"Ошибка при отмене сброса: {e}")
    else:
        await callback.message.edit_text("Выберите категорию:", reply_markup=get_categories_keyboard())

# ---------- К категориям и в главное меню ----------
@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await cleanup_practice(user_id, callback.bot, callback.message.chat.id, send_message=False)
    await callback.message.edit_text("✔️ Выберите категорию слов, которые хотите потренировать:", reply_markup=get_categories_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await cleanup_practice(user_id, callback.bot, callback.message.chat.id, send_message=False)
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.message(WordsState.category_chosen, ~F.text)
async def non_text_input(message: Message, state: FSMContext):
    await message.answer("Отправьте текстовый ответ.")

# ========== ОБЁРТКА ДЛЯ СОВМЕСТИМОСТИ С ИМПОРТОМ ИЗ start.py ==========
async def start_words(event, state: FSMContext):
    """Обёртка для вызова words_start из других модулей (например, start.py)"""
    await words_start(event, state)