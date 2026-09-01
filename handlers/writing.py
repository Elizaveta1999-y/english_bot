import json
import os
import re
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.deepseek_writing import check_writing
from utils.db import (
    get_writing_index, set_writing_index,
    get_writing_stats, update_writing_stats,
    reset_writing_progress, init_writing_session
)

logger = logging.getLogger(__name__)
router = Router()

# ---------- Загрузка заданий ----------
TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/writing_tasks.json")

LEVEL_MAP = {
    "beginner": "beginner",
    "intermediate": "intermediate",
    "advanced": "expert"
}

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

ALL_TASKS = load_tasks()

def _flatten_tasks(data):
    result = []
    if isinstance(data, list):
        for item in data:
            result.extend(_flatten_tasks(item))
    elif isinstance(data, dict):
        if "task_text" in data or "id" in data:
            result.append(data)
        else:
            for value in data.values():
                result.extend(_flatten_tasks(value))
    return result

def get_tasks_for_type_level(task_type: str, level_key: str):
    type_data = ALL_TASKS.get(task_type)
    if not type_data:
        return []
    if isinstance(type_data, dict):
        tasks = type_data.get(level_key, [])
        return _flatten_tasks(tasks)
    if isinstance(type_data, list):
        return _flatten_tasks(type_data)
    return []

FORBIDDEN_WORDS = [
    "насилие", "убить", "смерть", "кровь", "изнасилование",
    "секс", "порно", "эротика", "голый", "обнаженный",
    "экстремизм", "терроризм", "бомба", "оружие",
    "политика", "путин", "зеленский", "война", "санкции"
]

# ---------- ЛИМИТЫ ----------
MAX_WORDS = 500      # максимальное количество слов
MAX_CHARS = 3000     # максимальное количество символов

class WritingStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_answer = State()
    showing_progress = State()
    confirm_reset = State()

# ---------- Клавиатуры ----------
def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Email", callback_data="type_email")],
        [InlineKeyboardButton(text="📝 Эссе", callback_data="type_essay")],
        [InlineKeyboardButton(text="📱 Пост в соцсети", callback_data="type_post")],
        [InlineKeyboardButton(text="📖 История", callback_data="type_story")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_levels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Новичок", callback_data="level_beginner")],
        [InlineKeyboardButton(text="📚 Любитель", callback_data="level_intermediate")],
        [InlineKeyboardButton(text="🎓 Эксперт", callback_data="level_advanced")],
        [InlineKeyboardButton(text="Назад", callback_data="writing_back_to_types")]
    ])

def get_action_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data="writing_show_answer"),
            InlineKeyboardButton(text="Следующее задание", callback_data="writing_next_task")
        ],
        [
            InlineKeyboardButton(text="Завершить", callback_data="cancel_writing")
        ]
    ])

def get_reset_confirmation_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить", callback_data="confirm_reset_yes")],
        [InlineKeyboardButton(text="Назад", callback_data="confirm_reset_no")]
    ])

def get_progress_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="reset_progress")]
    ])

# ---------- Проверки ----------
def is_meaningful_english(text: str) -> bool:
    if not re.search(r'[a-zA-Z]', text):
        return False
    cleaned = re.sub(r'[^a-zA-Z\s]', '', text)
    words = cleaned.split()
    if len(words) < 3:
        return False
    meaningful = sum(1 for w in words if len(w) > 2)
    return meaningful >= len(words) * 0.5

def contains_forbidden(text: str) -> bool:
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in text_lower:
            return True
    return False

# ---------- Подсчёт предложений ----------
def count_sentences(text: str) -> int:
    text = text.replace('...', '.')
    parts = re.split(r'[.!?]+', text)
    sentences = [p.strip() for p in parts if p.strip() and len(p.split()) >= 3]
    return len(sentences)

SENTENCE_LIMITS = {
    "essay": {"beginner": 3, "intermediate": 4, "expert": 5},
    "post":   {"beginner": 3, "intermediate": 4, "expert": 6},
    "story":  {"beginner": 4, "intermediate": 6, "expert": 6}
}

# ================== ХЕНДЛЕРЫ КОМАНД / (В ПЕРВУЮ ОЧЕРЕДЬ) ==================
@router.message(WritingStates.choosing_type, F.text.startswith("/"))
@router.message(WritingStates.choosing_level, F.text.startswith("/"))
@router.message(WritingStates.waiting_answer, F.text.startswith("/"))
@router.message(WritingStates.showing_progress, F.text.startswith("/"))
@router.message(WritingStates.confirm_reset, F.text.startswith("/"))
async def handle_command_in_writing(message: Message, state: FSMContext):
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
    await message.answer("Практика завершена")
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)

# ---------- Entry ----------
@router.callback_query(F.data == "start_writing")
async def start_writing_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)

async def show_task_types(message: Message, edit: bool = False):
    text = "✍️ Письмо\n\nВыберите тип задания:"
    keyboard = get_types_keyboard()
    if edit:
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception as e:
            if "message is not modified" not in str(e):
                raise
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() is None:
        await state.set_state(WritingStates.choosing_type)
    await callback.answer()
    task_type = callback.data.split("_")[1]
    await state.update_data(task_type=task_type)
    await state.set_state(WritingStates.choosing_level)
    text = "Выберите уровень сложности:"
    try:
        await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

@router.callback_query(F.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() is None:
        await state.set_state(WritingStates.choosing_type)
        await callback.message.edit_text(
            "⚠️ Тип задания не выбран. Пожалуйста, выберите тип заново:",
            reply_markup=get_types_keyboard(),
            parse_mode="Markdown"
        )
        return
    await callback.answer()
    level = callback.data.split("_")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")

    if not task_type:
        await callback.message.edit_text(
            "⚠️ Тип задания не выбран. Пожалуйста, выберите тип заново:",
            reply_markup=get_types_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(WritingStates.choosing_type)
        return

    level_key = LEVEL_MAP.get(level, level)
    current_level = data.get("level")
    if current_level == level_key:
        await show_task(callback.message, state, edit=False)
        return

    tasks = get_tasks_for_type_level(task_type, level_key)
    if not tasks:
        await callback.message.edit_text(
            "Заданий для этого уровня пока нет. Выберите другой уровень:",
            reply_markup=get_levels_keyboard(),
            parse_mode="Markdown"
        )
        return

    await init_writing_session(user_id, task_type, level_key)
    index = await get_writing_index(user_id, task_type, level_key)
    if index >= len(tasks):
        index = 0
        await set_writing_index(user_id, task_type, level_key, index)

    await state.update_data(
        user_id=user_id,
        task_type=task_type,
        level=level_key,
        tasks=tasks,
        current_task=tasks[index],
        index=index,
        last_task_msg_id=None,
        progress_msg_id=None
    )

    await show_progress_card(callback.message, state, edit=True)
    await show_task(callback.message, state, edit=False)

# ---------- Карточка прогресса ----------
async def show_progress_card(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        return

    task_type = data.get("task_type")
    level = data.get("level")

    total_answered, total_score, session_answered, session_score = await get_writing_stats(user_id, task_type, level)

    type_names = {
        "email": "📧 Email",
        "essay": "📝 Эссе",
        "post": "📱 Пост",
        "story": "📖 История"
    }
    level_names = {
        "beginner": "🌱 Новичок",
        "intermediate": "📚 Любитель",
        "expert": "🎓 Эксперт"
    }

    mode_text = type_names.get(task_type, task_type)
    level_text = level_names.get(level, level)

    avg_score = round(total_score / total_answered, 1) if total_answered > 0 else 0

    card_text = (
        f"*Режим:* {mode_text}\n"
        f"*Уровень:* {level_text}\n\n"
        f"Напишите {task_type} согласно заданию.\n\n"
        f"Ваш средний балл: {avg_score}/5"
    )

    keyboard = get_progress_keyboard()
    try:
        if edit:
            await message.edit_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
            await state.update_data(progress_msg_id=message.message_id)
        else:
            sent = await message.answer(card_text, reply_markup=keyboard, parse_mode="Markdown")
            await state.update_data(progress_msg_id=sent.message_id)
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

    await state.set_state(WritingStates.showing_progress)

# ---------- Показ задания ----------
async def show_task(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    task = data.get("current_task")
    if not task:
        await message.answer("Ошибка: задание не найдено.")
        return

    while isinstance(task, list):
        if not task:
            await message.answer("Ошибка: пустой список заданий.")
            return
        task = task[0]

    if not isinstance(task, dict):
        await message.answer("Ошибка: неверный формат задания.")
        return

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
        await state.update_data(last_task_msg_id=None)

    task_text = task.get('task_text', 'Текст задания отсутствует')
    expected_length = task.get('expected_length', 'не указан')
    task_type = data.get("task_type")

    text = f"{task_text}\n\n"
    if task_type in ["email", "post"] and expected_length != 'не указан':
        text += f"Объём: {expected_length}\n"
    # Добавляем предупреждение о лимите
    text += f"\n_Максимум: {MAX_WORDS} слов (около {MAX_CHARS} символов)._"

    keyboard = get_action_keyboard()
    try:
        if edit:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
            await state.update_data(last_task_msg_id=sent_msg.message_id)
    except Exception as e:
        if "message is not modified" not in str(e):
            raise

    await state.set_state(WritingStates.waiting_answer)

# ---------- СБРОС ПРОГРЕССА ----------
@router.callback_query(F.data == "reset_progress")
async def reset_progress_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task_type = data.get("task_type")

    if not task_type:
        await callback.message.answer("Ошибка: тип задания не найден. Начните заново.")
        return

    text = "Вы уверенны? Средний балл обнулится, задания будут даны с самого начала."
    keyboard = get_reset_confirmation_keyboard()

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

    await state.set_state(WritingStates.confirm_reset)

@router.callback_query(WritingStates.confirm_reset, F.data == "confirm_reset_yes")
async def reset_progress_yes(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])

    if not tasks:
        await callback.message.answer("Нет заданий для сброса.")
        await state.clear()
        return

    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await reset_writing_progress(user_id, task_type, level)

    await state.update_data(index=0, current_task=tasks[0], last_task_msg_id=None, progress_msg_id=None)

    await callback.message.answer("Прогресс сброшен. Задания даны с начала.")

    await show_progress_card(callback.message, state, edit=False)
    await show_task(callback.message, state, edit=False)

@router.callback_query(WritingStates.confirm_reset, F.data == "confirm_reset_no")
async def reset_progress_no(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_progress_card(callback.message, state, edit=True)
    await show_task(callback.message, state, edit=False)

# ---------- ОБРАБОТКА ОТВЕТА (после команд) ----------
@router.message(WritingStates.waiting_answer, F.text)
async def handle_user_answer(message: Message, state: FSMContext):
    user_text = message.text

    # 1. Проверка на осмысленность (английский, не слишком коротко)
    if not is_meaningful_english(user_text):
        if re.search(r'[а-яА-Я]', user_text) and not re.search(r'[a-zA-Z]', user_text):
            await message.answer("Ваш ответ должен быть на английском языке. Пожалуйста, перепишите.")
        else:
            await message.answer("Ваш ответ не содержит осмысленного текста.\nПожалуйста, перепишите.")
        return

    # 2. Проверка на запрещённые слова
    if contains_forbidden(user_text):
        await message.answer("Текст содержит неподходящие для изучения темы. Пожалуйста, напишите что-то другое.")
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Ошибка: пользователь не найден. Начните заново.")
        await state.clear()
        return

    task = data.get("current_task")
    while isinstance(task, list):
        if not task:
            await message.answer("Ошибка: пустой список заданий.")
            return
        task = task[0]
    if not task:
        await message.answer("Ошибка: задание не найдено. Начните заново.")
        await state.clear()
        return

    if not isinstance(task, dict):
        await message.answer("Ошибка: неверный формат задания. Перезапустите режим.")
        await state.clear()
        return

    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index", 0)
    tasks = data.get("tasks", [])

    # ---------- НОВЫЕ ПРОВЕРКИ НА МАКСИМАЛЬНУЮ ДЛИНУ ----------
    word_count = len(user_text.split())
    char_count = len(user_text)

    if word_count > MAX_WORDS:
        await message.answer(
            f"❌ Ваш ответ слишком длинный.\n"
            f"Максимальное количество слов: {MAX_WORDS}.\n"
            f"У вас: {word_count} слов.\n\n"
            f"Пожалуйста, сократите текст до {MAX_WORDS} слов и отправьте снова."
        )
        return

    if char_count > MAX_CHARS:
        await message.answer(
            f"❌ Ваш ответ слишком длинный.\n"
            f"Максимальное количество символов: {MAX_CHARS}.\n"
            f"У вас: {char_count} символов.\n\n"
            f"Пожалуйста, сократите текст до {MAX_CHARS} символов и отправьте снова."
        )
        return

    # ---- Проверка длины (минимальная и максимальная для конкретного типа) ----
    if task_type == "email":
        count = len(user_text.split())
        if level == "beginner":
            min_count = 30
        elif level == "intermediate":
            min_count = 60
        else:
            min_count = 80
        max_count = 150
        unit = "слов"
    else:
        count = count_sentences(user_text)
        limits = SENTENCE_LIMITS.get(task_type, {})
        min_count = limits.get(level, 3)
        max_count = 10
        unit = "предложений"

    if count < min_count:
        await message.answer(f"Слишком коротко. Напишите не менее {min_count} {unit}.")
        return
    if count > max_count:
        await message.answer(f"Слишком длинно! Сократите до {max_count} {unit}.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        feedback, score = await check_writing(
            task_text=task.get('task_text', ''),
            user_answer=user_text,
            level=level,
            keywords=task.get('keywords', []),
            task_type=task_type
        )
    except Exception as e:
        await message.answer("Ошибка при обращении к ИИ. Попробуйте позже.")
        return

    # --- СОХРАНЯЕМ СТАТИСТИКУ ---
    await update_writing_stats(user_id, task_type, level, score)

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
        await state.update_data(last_task_msg_id=None)

    # --- ОТПРАВЛЯЕМ ФИДБЕК С ОЦЕНКОЙ ---
    feedback_with_score = f"*Оценка:* {score}/5\n\n{feedback}"
    await message.answer(feedback_with_score, parse_mode="Markdown")

    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await show_progress_card(message, state, edit=True)
        except Exception:
            pass

    await go_to_next_task(message, state, user_id, task_type, level, index, tasks)

async def go_to_next_task(message: Message, state: FSMContext, user_id: int, task_type: str, level: str, current_index: int, tasks: list):
    next_index = current_index + 1
    if next_index >= len(tasks):
        next_index = 0
    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(message, state, edit=False)

# ---------- Кнопки управления ----------
@router.callback_query(WritingStates.waiting_answer, F.data == "writing_next_task")
async def next_task_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index", 0)
    tasks = data.get("tasks", [])
    user_id = callback.from_user.id

    if not tasks:
        await callback.message.answer("Нет заданий.")
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    next_index = index + 1
    if next_index >= len(tasks):
        next_index = 0
    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(callback.message, state, edit=False)

@router.callback_query(WritingStates.waiting_answer, F.data == "writing_show_answer")
async def show_answer_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task = data.get("current_task")
    while isinstance(task, list):
        if not task:
            await callback.message.answer("Задание не найдено.")
            return
        task = task[0]
    if not task:
        await callback.message.answer("Задание не найдено.")
        return

    sample = task.get("sample_answer", "Пример ответа отсутствует.")
    await callback.message.answer(f"Пример ответа:\n\n{sample}")

    await callback.message.edit_reply_markup(reply_markup=None)

    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index", 0)
    tasks = data.get("tasks", [])
    user_id = callback.from_user.id

    next_index = index + 1
    if next_index >= len(tasks):
        next_index = 0
    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(callback.message, state, edit=False)

# ---------- ЗАВЕРШЕНИЕ СЕССИИ (кнопка "Завершить") ----------
@router.callback_query(WritingStates.waiting_answer, F.data == "cancel_writing")
async def cancel_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")

    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    total_answered, total_score, session_answered, session_score = await get_writing_stats(user_id, task_type, level)

    if session_answered > 0:
        avg_session = round(session_score / session_answered, 1)
        await callback.message.answer(
            f"Сессия завершена! 🙌🏻\n"
            f"Вы выполнили {session_answered} заданий.\n"
            f"Средний балл за сессию: {avg_session}."
        )
    else:
        await callback.message.answer(
            "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
        )

    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

# ---------- Навигация ----------
@router.callback_query(F.data == "writing_back_to_types")
async def writing_back_to_types(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() is None:
        await state.set_state(WritingStates.choosing_type)
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_writing(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() is None:
        await callback.answer("Режим не активен.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    data = await state.get_data()
    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

# ---------- Не текстовые сообщения ----------
@router.message(WritingStates.waiting_answer, F.content_type.in_({'photo', 'document', 'audio', 'voice', 'video', 'sticker', 'animation', 'video_note', 'contact', 'location'}))
async def handle_non_text_in_writing(message: Message, state: FSMContext):
    await message.answer("Введите текстовый ответ.")

# =====================================================================
# ФУНКЦИЯ ДЛЯ ВЫЗОВА ИЗ START.PY
# =====================================================================
async def start_writing(callback: CallbackQuery, state: FSMContext):
    """
    Запускает режим Письмо из внешнего вызова (например, из start.py).
    """
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)