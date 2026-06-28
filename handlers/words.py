import os
import json
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import redis.asyncio as redis

router = Router()

# ---------- Конфигурация ----------
WORDS_DIR = "data/words/"
META_FILE = "data/categories_meta.json"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

with open(META_FILE, "r", encoding="utf-8") as f:
    CATEGORIES_META = json.load(f)

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

redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

# ---------- FSM ----------
class WordsState(StatesGroup):
    category_chosen = State()

# ---------- Сессии в памяти ----------
user_sessions = {}

# ---------- Клавиатуры ----------
def get_categories_keyboard():
    items = list(AVAILABLE_CATEGORIES.items())
    keyboard = []
    for i in range(0, len(items), 2):
        row = []
        key, meta = items[i]
        row.append(InlineKeyboardButton(text=meta["label"], callback_data=f"word_cat_{key}"))
        if i + 1 < len(items):
            key2, meta2 = items[i + 1]
            row.append(InlineKeyboardButton(text=meta2["label"], callback_data=f"word_cat_{key2}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_word_card_keyboard():
    # Кнопки в одной строке
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data="word_show_answer"),
            InlineKeyboardButton(text="Завершить", callback_data="word_finish")
        ]
    ])

def get_finish_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="К категориям", callback_data="back_to_categories")]
    ])

# ---------- Вспомогательные ----------
def normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip().lower())

def load_words(category_key: str):
    file_path = os.path.join(WORDS_DIR, f"{category_key}.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def get_user_index(user_id: int, category_key: str) -> int:
    r = await get_redis()
    val = await r.get(f"word_progress:{user_id}:{category_key}")
    return int(val) if val else 0

async def set_user_index(user_id: int, category_key: str, index: int):
    r = await get_redis()
    await r.set(f"word_progress:{user_id}:{category_key}", str(index))

def is_correct(user_answer: str, correct_answer: str) -> bool:
    user_answer = normalize_text(user_answer)
    variants = re.split(r'\s*[,/]\s*', correct_answer.lower())
    if not variants:
        variants = [correct_answer.lower()]
    return user_answer in variants

async def show_answer_with_example(message, word_data, is_correct: bool = False):
    """
    Отправляет ответ с примером.
    is_correct=True → пишем "Верно! Правильный ответ: ..."
    is_correct=False → просто "Правильный ответ: ..."
    """
    answer = word_data["answer"]
    example = word_data.get("example")
    if is_correct:
        text = f"Верно! Правильный ответ: {answer}"
    else:
        text = f"Правильный ответ: {answer}"
    if example:
        text += f"\n\n<i>{example}</i>"
    await message.answer(text, parse_mode="HTML")

async def disable_buttons_and_send_next(message, user_id, session, edit_message):
    """
    Редактирует сообщение с карточкой (убирает кнопки) и отправляет новую карточку.
    edit_message – исходное сообщение карточки (Message или CallbackQuery.message)
    """
    # Редактируем карточку — убираем клавиатуру
    if isinstance(edit_message, CallbackQuery):
        msg = edit_message.message
    else:
        msg = edit_message
    await msg.edit_text(msg.text, reply_markup=None, parse_mode="HTML")

    # Отправляем новое слово (новым сообщением)
    await show_word(message, user_id, session, edit=False)

async def show_word(message_or_callback, user_id: int, session: dict, edit: bool = False):
    """Показывает карточку слова (слово: _____)"""
    words = session["words"]
    index = session["index"]
    total = len(words)
    if total == 0:
        await message_or_callback.edit_text("В этой категории нет слов.", reply_markup=get_categories_keyboard())
        return
    if index >= total:
        index = 0
        session["index"] = 0
        await set_user_index(user_id, session["category"], 0)

    word = words[index]
    session["current_word"] = word

    text = f"{word['word']}: _____"
    keyboard = get_word_card_keyboard()
    if edit:
        await message_or_callback.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="HTML")

# ---------- Хендлеры ----------
@router.callback_query(F.data == "start_words")
@router.message(Command("words"))
async def words_start(event, state: FSMContext):
    await state.clear()
    if isinstance(event, Message):
        await event.answer("Выберите категорию слов:", reply_markup=get_categories_keyboard())
    elif isinstance(event, CallbackQuery):
        await event.message.edit_text("Выберите категорию слов:", reply_markup=get_categories_keyboard())
        await event.answer()

@router.callback_query(F.data.startswith("word_cat_"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    category_key = callback.data.split("_")[-1]

    try:
        words = load_words(category_key)
    except FileNotFoundError:
        await callback.answer("Файл с этой категорией не найден.", show_alert=True)
        return
    if not words:
        await callback.answer("В этой категории пока нет слов.", show_alert=True)
        return

    start_index = await get_user_index(user_id, category_key)

    user_sessions[user_id] = {
        "words": words,
        "index": start_index,
        "correct": 0,
        "wrong": 0,
        "category": category_key,
        "current_word": None
    }

    # Приветствие
    meta = AVAILABLE_CATEGORIES.get(category_key, {})
    instruction = meta.get("instruction", "Переведите слово.")
    welcome_text = f"<b>Режим: «{meta.get('label', category_key)}»</b>\n{instruction}"
    await callback.message.edit_text(welcome_text, parse_mode="HTML")

    # Первая карточка
    await show_word(callback.message, user_id, user_sessions[user_id], edit=False)

    await state.set_state(WordsState.category_chosen)
    await callback.answer()

@router.message(WordsState.category_chosen, F.text)
async def handle_answer(message: Message, state: FSMContext):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await message.answer("Пожалуйста, сначала выберите категорию через кнопку 'Words'.")
        return

    current_word = session.get("current_word")
    if not current_word:
        await show_word(message, user_id, session, edit=False)
        return

    correct_answer = current_word["answer"]
    user_answer = message.text

    if is_correct(user_answer, correct_answer):
        session["correct"] += 1
        # Показываем ответ с примером (с "Верно!")
        await show_answer_with_example(message, current_word, is_correct=True)
        # Увеличиваем индекс и сохраняем
        session["index"] += 1
        if session["index"] >= len(session["words"]):
            session["index"] = 0
        await set_user_index(user_id, session["category"], session["index"])
        # Редактируем карточку (убираем кнопки) и отправляем новую
        await disable_buttons_and_send_next(message, user_id, session, message)
    else:
        session["wrong"] += 1
        await message.answer("Неверно, попробуйте ещё раз.")

@router.callback_query(F.data == "word_show_answer", WordsState.category_chosen)
async def show_answer(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await callback.answer("Сессия не найдена. Выберите категорию заново.", show_alert=True)
        return

    current_word = session.get("current_word")
    if not current_word:
        await callback.answer("Ошибка. Попробуйте заново.", show_alert=True)
        return

    # Показываем ответ с примером (без "Верно!")
    await show_answer_with_example(callback.message, current_word, is_correct=False)

    # Увеличиваем индекс и сохраняем
    session["index"] += 1
    if session["index"] >= len(session["words"]):
        session["index"] = 0
    await set_user_index(user_id, session["category"], session["index"])

    # Редактируем карточку (убираем кнопки) и отправляем новую
    await disable_buttons_and_send_next(callback.message, user_id, session, callback)

    await callback.answer()

@router.callback_query(F.data == "word_finish", WordsState.category_chosen)
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
        stats_text = "Вы не дали ни одного ответа."
    else:
        stats_text = f"Правильно: {correct}\nОшибок: {wrong}\nТочность: {correct/total*100:.1f}%"

    await callback.message.edit_text(
        f"Сессия завершена!\n\n{stats_text}",
        reply_markup=get_finish_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user_sessions.pop(user_id, None)
    await callback.message.edit_text("Выберите категорию слов:", reply_markup=get_categories_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_sessions.pop(user_id, None)
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()