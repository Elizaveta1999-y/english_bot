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
    logger.info("=== WRITING TASKS LOADED ===")
    logger.info(f"Keys: {list(data.keys())}")
    for task_type, levels in data.items():
        logger.info(f"  {task_type}: {list(levels.keys()) if isinstance(levels, dict) else 'list'}")
    return data

ALL_TASKS = load_tasks()

def get_tasks_for_type_level(task_type: str, level_key: str):
    type_data = ALL_TASKS.get(task_type)
    if not type_data:
        return []

    tasks = []
    if isinstance(type_data, dict):
        tasks = type_data.get(level_key, [])
        if not tasks:
            for key, value in type_data.items():
                if isinstance(value, list):
                    tasks = value
                    break
    elif isinstance(type_data, list):
        tasks = type_data

    if tasks and isinstance(tasks[0], list):
        flat = []
        for sublist in tasks:
            if isinstance(sublist, list):
                flat.extend(sublist)
            else:
                flat.append(sublist)
        tasks = flat

    tasks = [item for item in tasks if isinstance(item, dict)]
    return tasks

# ---------- Стоп-слова ----------
FORBIDDEN_WORDS = [
    "насилие", "убить", "смерть", "кровь", "изнасилование",
    "секс", "порно", "эротика", "голый", "обнаженный",
    "экстремизм", "терроризм", "бомба", "оружие",
    "политика", "путин", "зеленский", "война", "санкции"
]

# ---------- States ----------
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
        [InlineKeyboardButton(text="🔙 Назад к типам", callback_data="back_to_types")]
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
        [InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="reset_progress")]
    ])

# ---------- Проверки ----------
def is_meaningful_english(text: str) -> bool:
    # Если нет латинских букв – считаем бессмысленным
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

# ---------- Entry ----------
@router.callback_query(F.data == "start_writing")
async def start_writing_mode(callback: CallbackQuery):
    await callback.answer()
    await show_task_types(callback.message, edit=True)

async def show_task_types(message: Message, edit: bool = False):
    text = "✍️ Письмо\n\nВыберите тип задания:"
    keyboard = get_types_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_type = callback.data.split("_")[1]
    await state.update_data(task_type=task_type)
    await state.set_state(WritingStates.choosing_level)
    text = "Выберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
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
    tasks = get_tasks_for_type_level(task_type, level_key)

    if not tasks:
        logger.warning(f"Нет заданий для {task_type} уровня {level_key}")
        available = ', '.join(ALL_TASKS.get(task_type, {}).keys()) if isinstance(ALL_TASKS.get(task_type), dict) else 'список'
        await callback.message.edit_text(
            f"Заданий для {task_type} уровня {level_key} пока нет.\n"
            f"Доступные уровни: {available if available else 'нет'}"
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
        logger.error("user_id not found in state")
        return

    task_type = data.get("task_type")
    level = data.get("level")

    total_answered, total_score, session_answered, session_score = await get_writing_stats(user_id, task_type, level)
    logger.info(f"Progress for user {user_id}: total_answered={total_answered}, total_score={total_score}")

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

    if total_answered > 0:
        avg_score = round(total_score / total_answered, 1)
    else:
        avg_score = 0

    card_text = (
        f"*Режим:* {mode_text}\n"
        f"*Уровень:* {level_text}\n\n"
        f"Напишите {task_type} согласно заданию.\n\n"
        f"Ваш средний балл: {avg_score}/5"
    )

    keyboard = get_progress_keyboard()
    if edit:
        sent = await message.edit_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        sent = await message.answer(card_text, reply_markup=keyboard, parse_mode="Markdown")
    
    await state.update_data(progress_msg_id=sent.message_id)
    await state.set_state(WritingStates.showing_progress)

# ---------- Показ задания ----------
async def show_task(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    task = data.get("current_task")
    if not task:
        await message.answer("Ошибка: задание не найдено.")
        return

    if isinstance(task, list):
        task = task[0] if task else None
    if not task:
        await message.answer("Ошибка: пустой список заданий.")
        return

    # Удаляем клавиатуру у предыдущего сообщения с заданием
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
    # Объём показываем ТОЛЬКО для email и post
    if task_type in ["email", "post"] and expected_length != 'не указан':
        text += f"Объём: {expected_length}\n"
    # Рекомендуемые слова УБРАНЫ ВЕЗДЕ

    keyboard = get_action_keyboard()
    
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        await state.update_data(last_task_msg_id=sent_msg.message_id)
    
    await state.set_state(WritingStates.waiting_answer)

# ---------- Сброс прогресса ----------
@router.callback_query(F.data == "reset_progress")
async def reset_progress_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task_type = data.get("task_type")
    if not task_type:
        await callback.message.answer("Ошибка: тип задания не найден. Начните заново.")
        return
    
    # Убираем клавиатуру у карточки прогресса
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
    
    text = "Вы уверены? Средний балл будет обнулен. Все задания будут даны с самого начала."
    keyboard = get_reset_confirmation_keyboard()
    await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WritingStates.confirm_reset)

@router.callback_query(F.data == "confirm_reset_yes", WritingStates.confirm_reset)
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

    await reset_writing_progress(user_id, task_type, level)
    await state.update_data(index=0, current_task=tasks[0], last_task_msg_id=None, progress_msg_id=None)

    # Редактируем текущее сообщение с подтверждением (убираем клавиатуру)
    await callback.message.edit_text("Прогресс обнулился. Задания даны с начала.", reply_markup=None)

    # Отправляем НОВУЮ карточку прогресса
    await show_progress_card(callback.message, state, edit=False)
    # Отправляем НОВОЕ задание
    await show_task(callback.message, state, edit=False)

@router.callback_query(F.data == "confirm_reset_no", WritingStates.confirm_reset)
async def reset_progress_no(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    # Удаляем сообщение с подтверждением
    await callback.message.delete()
    # Показываем карточку прогресса (без изменений) и текущее задание
    await show_progress_card(callback.message, state, edit=False)
    await show_task(callback.message, state, edit=False)

# ---------- Обработка ответа ----------
@router.message(WritingStates.waiting_answer, F.text)
async def handle_user_answer(message: Message, state: FSMContext):
    user_text = message.text

    if not is_meaningful_english(user_text):
        await message.answer(
            "Ваш ответ не содержит осмысленного текста.\n"
            "Пожалуйста, перепишите."
        )
        return

    if contains_forbidden(user_text):
        await message.answer(
            "Текст содержит неподходящие для изучения темы. Пожалуйста, напишите что-то другое."
        )
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("Ошибка: пользователь не найден. Начните заново.")
        await state.clear()
        return

    task = data.get("current_task")
    if isinstance(task, list):
        task = task[0] if task else None
    if not task:
        await message.answer("Ошибка: задание не найдено. Начните заново.")
        await state.clear()
        return

    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index", 0)
    tasks = data.get("tasks", [])

    word_count = len(user_text.split())
    if word_count < 10:
        await message.answer("Слишком коротко! Напишите не менее 10 слов.")
        return
    if word_count > 150:
        await message.answer("Слишком длинно! Сократите до 150 слов.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        feedback, score = await check_writing(
            task_text=task.get('task_text', ''),
            user_answer=user_text,
            level=level,
            keywords=task.get('keywords', [])
        )
    except Exception as e:
        await message.answer("Ошибка при обращении к ИИ. Попробуйте позже.")
        return

    logger.info(f"Updating stats: user={user_id}, type={task_type}, level={level}, score={score}")
    await update_writing_stats(user_id, task_type, level, score)

    # Убираем клавиатуру у предыдущего сообщения с заданием
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

    # Отправляем фидбек
    await message.answer(f"{feedback}\n\nОценка: {score}/5")

    # Обновляем карточку прогресса (редактируем существующую)
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            # Перерисовываем карточку прогресса с новыми данными
            await show_progress_card(message, state, edit=True)
        except Exception as e:
            logger.error(f"Failed to update progress card: {e}")

    # Переход к следующему заданию
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
@router.callback_query(F.data == "writing_next_task")
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

    # Убираем клавиатуру у текущего сообщения
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

@router.callback_query(F.data == "writing_show_answer")
async def show_answer_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task = data.get("current_task")
    if isinstance(task, list):
        task = task[0] if task else None
    if not task:
        await callback.message.answer("Задание не найдено.")
        return

    sample = task.get("sample_answer", "Пример ответа отсутствует.")
    await callback.message.answer(f"Пример ответа:\n\n{sample}")

    # Убираем клавиатуру у текущего сообщения
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

# ---------- Завершение ----------
@router.callback_query(F.data == "cancel_writing")
async def cancel_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")

    total_answered, total_score, session_answered, session_score = await get_writing_stats(user_id, task_type, level)

    # Убираем ВСЕ клавиатуры
    await callback.message.edit_reply_markup(reply_markup=None)
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

    if session_answered > 0:
        avg_session = round(session_score / session_answered, 1)
        await callback.message.answer(
            f"Сессия завершена! Вы выполнили {session_answered} заданий. "
            f"Средний балл за сессию: {avg_session}. Отличная работа! 💪"
        )
    else:
        await callback.message.answer(
            "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
        )

    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

# ---------- Навигация ----------
@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    # Убираем ВСЕ клавиатуры
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