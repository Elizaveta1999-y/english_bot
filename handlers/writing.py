import json
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.deepseek_writing import check_writing
import redis.asyncio as redis

router = Router()

# ---------- Загрузка заданий ----------
TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/writing_tasks.json")

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

ALL_TASKS = load_tasks()

print("=== WRITING TASKS LOADED ===")
print(f"Keys: {list(ALL_TASKS.keys())}")

# ---------- Redis для прогресса ----------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

async def get_writing_index(user_id: int, task_type: str, level: str) -> int:
    r = await get_redis()
    key = f"writing_progress:{user_id}:{task_type}:{level}"
    val = await r.get(key)
    return int(val) if val else 0

async def set_writing_index(user_id: int, task_type: str, level: str, index: int):
    r = await get_redis()
    key = f"writing_progress:{user_id}:{task_type}:{level}"
    await r.set(key, str(index))

# ---------- Состояния FSM ----------
class WritingStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_answer = State()

# ---------- Клавиатуры ----------
def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📧 Email", callback_data="type_email"),
            InlineKeyboardButton(text="📝 Эссе", callback_data="type_essay")
        ],
        [
            InlineKeyboardButton(text="📱 Пост в соцсети", callback_data="type_post"),
            InlineKeyboardButton(text="💬 Диалог", callback_data="type_dialogue")
        ],
        [
            InlineKeyboardButton(text="📖 История", callback_data="type_story"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ])

def get_levels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌱 Новичок", callback_data="level_beginner"),
            InlineKeyboardButton(text="🔥 Любитель", callback_data="level_intermediate")
        ],
        [
            InlineKeyboardButton(text="🧠 Эксперт", callback_data="level_advanced"),
            InlineKeyboardButton(text="🔙 Назад к типам", callback_data="back_to_types")
        ]
    ])

def get_action_keyboard():
    """Клавиатура с кнопками: Показать ответ, Следующее задание, Завершить (без смайликов)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data="writing_show_answer"),
            InlineKeyboardButton(text="Следующее задание", callback_data="writing_next_task")
        ],
        [
            InlineKeyboardButton(text="Завершить", callback_data="cancel_writing")
        ]
    ])

# ---------- ВХОД В РЕЖИМ ----------
@router.callback_query(F.data == "start_writing")
async def start_writing_mode(callback: CallbackQuery):
    await callback.answer()
    await show_task_types(callback.message, edit=True)

# ---------- Показать типы ----------
async def show_task_types(message: Message, edit: bool = False):
    text = (
        "✍️ *Режим Письмо*\n\n"
        "Выберите тип задания:\n"
        "📧 *Email*\n"
        "📝 *Эссе*\n"
        "📱 *Пост*\n"
        "💬 *Диалог*\n"
        "📖 *История*"
    )
    keyboard = get_types_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ---------- Обработчики выбора типа ----------
@router.callback_query(F.data.startswith("type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_type = callback.data.split("_")[1]
    await state.update_data(task_type=task_type)
    await state.set_state(WritingStates.choosing_level)
    text = f"Вы выбрали тип: *{task_type.upper()}*.\nТеперь выберите уровень:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

# ---------- Выбор уровня и выдача задания с прогрессом ----------
@router.callback_query(F.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    level = callback.data.split("_")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    tasks = ALL_TASKS.get(task_type, {}).get(level, [])
    if not tasks:
        await callback.message.edit_text(f"Заданий для {task_type} уровня {level} пока нет.")
        return

    # Получаем текущий индекс
    index = await get_writing_index(user_id, task_type, level)
    if index >= len(tasks):
        index = 0
        await set_writing_index(user_id, task_type, level, index)

    task = tasks[index]
    await state.update_data(
        task_type=task_type,
        level=level,
        tasks=tasks,
        current_task=task,
        index=index
    )

    # Показываем задание
    await show_task(callback.message, state, edit=True)

# ---------- Функция показа задания ----------
async def show_task(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index", 0)
    tasks = data.get("tasks", [])
    if not task:
        await message.answer("Ошибка: задание не найдено.")
        return

    total = len(tasks)
    # Формируем текст задания (без смайликов)
    task_text = (
        f"Задание {index+1} из {total}\n\n"
        f"{task['task_text']}\n\n"
        f"Рекомендуемые слова (по желанию): {', '.join(task['keywords'])}\n"
        f"Объём: {task['expected_length']}"
    )

    keyboard = get_action_keyboard()
    if edit:
        await message.edit_text(task_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(task_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WritingStates.waiting_answer)

# ---------- Получение ответа пользователя ----------
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

    # Проверка длины (без смайликов в сообщениях)
    word_count = len(user_text.split())
    if word_count < 10:
        await message.answer("Слишком коротко! Напишите не менее 10 слов.")
        return
    if word_count > 150:
        await message.answer("Слишком длинно! Сократите до 150 слов.")
        return

    # Отправляем в DeepSeek для проверки
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        feedback = check_writing(
            task_text=task['task_text'],
            user_answer=user_text,
            level=level,
            keywords=task.get('keywords', [])
        )
    except Exception as e:
        await message.answer("Ошибка при обращении к ИИ. Попробуйте позже.")
        return

    # Отправляем фидбек (без смайликов в тексте фидбека, они могут быть только в самом фидбеке от ИИ)
    await message.answer(f"Результат проверки:\n\n{feedback}", parse_mode="Markdown")

    # Автоматически переходим к следующему заданию
    await go_to_next_task(message, state, user_id, task_type, level, index, tasks)

# ---------- Переход к следующему заданию ----------
async def go_to_next_task(message: Message, state: FSMContext, user_id: int, task_type: str, level: str, current_index: int, tasks: list):
    next_index = current_index + 1
    if next_index >= len(tasks):
        next_index = 0
        await message.answer("Вы прошли все задания! Начинаем заново.")

    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(message, state, edit=False)

# ---------- Обработчик кнопки "Следующее задание" ----------
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
        next_index = 0
        await callback.message.answer("Вы прошли все задания! Начинаем заново.")

    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(callback.message, state, edit=True)

# ---------- Обработчик кнопки "Показать ответ" ----------
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

    # Переходим к следующему заданию
    next_index = index + 1
    if next_index >= len(tasks):
        next_index = 0
        await callback.message.answer("Вы прошли все задания! Начинаем заново.")

    await set_writing_index(user_id, task_type, level, next_index)
    await state.update_data(
        index=next_index,
        current_task=tasks[next_index]
    )
    await show_task(callback.message, state, edit=True)

# ---------- Отмена и навигация ----------
@router.callback_query(F.data == "cancel_writing")
async def cancel_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)

@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)