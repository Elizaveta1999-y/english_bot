import json
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.deepseek_writing import check_writing
from database.db import get_writing_index, set_writing_index, reset_writing_progress

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
    print("=== WRITING TASKS LOADED ===")
    print(f"Keys: {list(data.keys())}")
    for task_type, levels in data.items():
        print(f"  {task_type}: {list(levels.keys())}")
    return data

ALL_TASKS = load_tasks()

# ---------- States ----------
class WritingStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_answer = State()
    showing_progress = State()

# ---------- Клавиатуры ----------
def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Email", callback_data="type_email")],
        [InlineKeyboardButton(text="📝 Эссе", callback_data="type_essay")],
        [InlineKeyboardButton(text="📱 Пост в соцсети", callback_data="type_post")],
        [InlineKeyboardButton(text="💬 Диалог", callback_data="type_dialogue")],
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
    text = f"Вы выбрали тип: {task_type.upper()}.\n\nВыберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    level = callback.data.split("_")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")

    level_key = LEVEL_MAP.get(level, level)
    tasks = ALL_TASKS.get(task_type, {}).get(level_key, [])
    if not tasks:
        available = ', '.join(ALL_TASKS.get(task_type, {}).keys())
        await callback.message.edit_text(
            f"Заданий для {task_type} уровня {level_key} пока нет.\n"
            f"Доступные уровни: {available if available else 'нет'}"
        )
        return

    index = await get_writing_index(user_id, task_type, level_key)
    if index >= len(tasks):
        index = 0
        await set_writing_index(user_id, task_type, level_key, index)

    await state.update_data(
        task_type=task_type,
        level=level_key,
        tasks=tasks,
        current_task=tasks[index],
        index=index
    )

    await show_progress_card(callback.message, state, edit=True)
    await show_task(callback.message, state, edit=False)

# ---------- Карточка прогресса ----------
async def show_progress_card(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])
    index = data.get("index", 0)
    total = len(tasks)

    type_names = {
        "email": "📧 Email",
        "essay": "📝 Эссе",
        "post": "📱 Пост",
        "dialogue": "💬 Диалог",
        "story": "📖 История"
    }
    level_names = {
        "beginner": "🌱 Новичок",
        "intermediate": "📚 Любитель",
        "expert": "🎓 Эксперт"
    }

    mode_text = type_names.get(task_type, task_type)
    level_text = level_names.get(level, level)
    progress_text = f"Задание {index+1} из {total}" if total > 0 else "Нет заданий"

    card_text = (
        f"Режим: {mode_text}\n"
        f"Уровень: {level_text}\n\n"
        "Внимательно прочитайте текст и восстановите порядок абзацев.\n\n"
        f"Ваш прогресс: {progress_text}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="reset_progress")]
    ])

    if edit:
        await message.edit_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(card_text, reply_markup=keyboard, parse_mode="Markdown")

    await state.set_state(WritingStates.showing_progress)

# ---------- Сброс прогресса ----------
@router.callback_query(F.data == "reset_progress", WritingStates.showing_progress)
async def reset_progress_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Прогресс сброшен!")
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])

    if not tasks:
        await callback.message.answer("Нет заданий для сброса.")
        return

    await reset_writing_progress(user_id, task_type, level)
    await state.update_data(index=0, current_task=tasks[0])

    await show_progress_card(callback.message, state, edit=True)
    await show_task(callback.message, state, edit=False)

# ---------- Показ задания ----------
async def show_task(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    task = data.get("current_task")
    if not task:
        await message.answer("Ошибка: задание не найдено.")
        return
    index = data.get("index", 0)
    tasks = data.get("tasks", [])
    total = len(tasks)

    task_text = task.get('task_text', 'Текст задания отсутствует')
    keywords = task.get('keywords', [])
    expected_length = task.get('expected_length', 'не указан')

    text = (
        f"Задание {index+1} из {total}\n\n"
        f"{task_text}\n\n"
        f"Рекомендуемые слова (по желанию): {', '.join(keywords)}\n"
        f"Объём: {expected_length}"
    )
    keyboard = get_action_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WritingStates.waiting_answer)

# ---------- Обработка ответа пользователя ----------
@router.message(WritingStates.waiting_answer, F.text)
async def handle_user_answer(message: Message, state: FSMContext):
    user_text = message.text
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index", 0)
    tasks = data.get("tasks", [])
    user_id = message.from_user.id

    if not task:
        await message.answer("Ошибка: задание не найдено. Начните заново.")
        await state.clear()
        return

    word_count = len(user_text.split())
    if word_count < 10:
        await message.answer("Слишком коротко! Напишите не менее 10 слов.")
        return
    if word_count > 150:
        await message.answer("Слишком длинно! Сократите до 150 слов.")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        feedback = check_writing(
            task_text=task.get('task_text', ''),
            user_answer=user_text,
            level=level,
            keywords=task.get('keywords', [])
        )
    except Exception as e:
        await message.answer("Ошибка при обращении к ИИ. Попробуйте позже.")
        return

    await message.answer(f"Результат проверки:\n\n{feedback}", parse_mode="Markdown")
    await go_to_next_task(message, state, user_id, task_type, level, index, tasks)

async def go_to_next_task(message: Message, state: FSMContext, user_id: int, task_type: str, level: str, current_index: int, tasks: list):
    next_index = current_index + 1
    if next_index >= len(tasks):
        next_index = 0  # бесшовный переход, без уведомления
    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_progress_card(message, state, edit=False)
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

    next_index = index + 1
    if next_index >= len(tasks):
        next_index = 0  # бесшовный переход

    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(callback.message, state, edit=True)
    await show_progress_card(callback.message, state, edit=False)

@router.callback_query(F.data == "writing_show_answer")
async def show_answer_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index", 0)
    tasks = data.get("tasks", [])
    user_id = callback.from_user.id

    if not task:
        await callback.message.answer("Задание не найдено.")
        return

    sample = task.get("sample_answer", "Пример ответа отсутствует.")
    await callback.message.answer(f"Пример ответа:\n\n{sample}")

    next_index = index + 1
    if next_index >= len(tasks):
        next_index = 0  # бесшовный переход

    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(callback.message, state, edit=True)
    await show_progress_card(callback.message, state, edit=False)

# ---------- Выход из режима ----------
@router.callback_query(F.data == "cancel_writing")
async def cancel_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Режим письма завершён. Для возврата в главное меню нажмите /start")
    await state.clear()

@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Вы вышли в главное меню. Используйте /start для возврата.")
    await state.clear()

