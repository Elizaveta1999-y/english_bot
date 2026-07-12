import json
import os
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from data.users import get_user_state, set_user_state
import redis.asyncio as redis

router = Router()

# ---------- Загрузка заданий ----------
TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/writing_tasks.json")

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

ALL_TASKS = load_tasks()

# ЛОГ ПРИ ЗАГРУЗКЕ
print("=== WRITING TASKS LOADED ===")
print(f"Keys: {list(ALL_TASKS.keys())}")
for k in ALL_TASKS:
    print(f"  {k}: {list(ALL_TASKS[k].keys())}")
    for level in ALL_TASKS[k]:
        print(f"    {level}: {len(ALL_TASKS[k][level])} tasks")

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

def get_action_keyboard(short_type: str, level: str, index: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Показать пример", callback_data=f"writing_show_sample:{short_type}:{level}:{index}"),
            InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_writing")
        ]
    ])

# ---------- Показать типы ----------
async def show_task_types(message: Message, edit: bool = False):
    text = (
        "✍️ *Режим Письмо*\n\n"
        "Выберите тип задания:\n"
        "📧 *Email* – письмо другу или коллеге\n"
        "📝 *Эссе* – выражение своего мнения\n"
        "📱 *Пост* – подпись для соцсетей\n"
        "💬 *Диалог* – сценарий разговора\n"
        "📖 *История* – рассказ по ключевым словам"
    )
    keyboard = get_types_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ---------- Обработчики ----------
@router.callback_query(F.data.startswith("type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_type = callback.data.split("_")[1]  # email, essay, post, dialogue, story
    await state.update_data(task_type=task_type)
    await state.set_state(WritingStates.choosing_level)
    text = f"Вы выбрали тип: *{task_type.upper()}*.\nТеперь выберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    level = callback.data.split("_")[1]  # beginner, intermediate, advanced
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")

    # ЛОГИ
    print(f"!!! level_chosen CALLED: task_type={task_type}, level={level}")

    # Получаем список заданий для этого типа и уровня
    tasks = ALL_TASKS.get(task_type, {}).get(level, [])
    print(f"!!! tasks count = {len(tasks)}")
    print(f"!!! ALL_TASKS keys: {list(ALL_TASKS.keys())}")
    if task_type in ALL_TASKS:
        print(f"!!! levels for {task_type}: {list(ALL_TASKS[task_type].keys())}")

    if not tasks:
        await callback.message.edit_text(
            f"😕 Заданий для типа *{task_type}* уровня *{level}* пока нет.\n"
            f"Пожалуйста, выберите другой уровень или тип задания.",
            parse_mode="Markdown"
        )
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
        index=index,
        tasks=tasks,
        current_task=task
    )

    # Формируем сообщение с заданием
    message_text = (
        f"📝 *Задание #{index+1} из {len(tasks)}*\n\n"
        f"{task['task_text']}\n\n"
        f"🔑 *Ключевые слова:* {', '.join(task['keywords'])}\n"
        f"📏 *Объём:* {task['expected_length']}\n\n"
        f"✍️ Напишите свой ответ в чат."
    )
    keyboard = get_action_keyboard(task_type, level, index)
    await callback.message.edit_text(message_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(WritingStates.waiting_answer)

# ---------- Получение ответа пользователя ----------
@router.message(WritingStates.waiting_answer, F.text)
async def handle_user_answer(message: Message, state: FSMContext):
    user_text = message.text
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    level = data.get("level")
    index = data.get("index")
    tasks = data.get("tasks", [])
    user_id = message.from_user.id

    if not task:
        await message.answer("Ошибка: задание не найдено. Начните заново.")
        await state.clear()
        return

    # 1. Проверка длины
    word_count = len(user_text.split())
    if word_count < 10:
        await message.answer("❌ Слишком коротко! Напишите не менее 10 слов.")
        return
    if word_count > 100:
        await message.answer("⚠️ Слишком длинно! Сократите до 100 слов.")
        return

    # 2. Проверка наличия ключевых слов
    keywords = task.get("keywords", [])
    has_keyword = any(kw in user_text.lower() for kw in keywords)
    if not has_keyword:
        await message.answer(
            f"🤔 Вы не использовали ключевые слова: *{', '.join(keywords)}*.\n"
            f"Попробуйте перефразировать ответ с этими словами.",
            parse_mode="Markdown"
        )
        return

    # 3. Здесь будет вызов DeepSeek (пока заглушка)
    await message.answer(
        "✅ *Текст принят!*\n\n"
        "🤖 *ИИ-проверка (заглушка):*\n"
        "Ваш текст содержит ключевые слова и достаточен по объёму.\n\n"
        "📊 *Результат:* 5/6 баллов.\n"
        "✍️ *Исправленный вариант:* " + user_text.replace("cook", "cooked").replace("go", "went") + "\n\n"
        "*(Скоро здесь появится полноценная проверка через DeepSeek!)*",
        parse_mode="Markdown"
    )

    # 4. Переход к следующему заданию
    next_index = index + 1
    if next_index >= len(tasks):
        next_index = 0
        await message.answer("🎉 Вы прошли все задания! Начинаем заново.")
    await set_writing_index(user_id, task_type, level, next_index)

    # Обновляем состояние для следующего задания
    await state.update_data(index=next_index)
    if next_index < len(tasks):
        next_task = tasks[next_index]
        await state.update_data(current_task=next_task)
        # Отправляем следующее задание
        message_text = (
            f"📝 *Задание #{next_index+1} из {len(tasks)}*\n\n"
            f"{next_task['task_text']}\n\n"
            f"🔑 *Ключевые слова:* {', '.join(next_task['keywords'])}\n"
            f"📏 *Объём:* {next_task['expected_length']}\n\n"
            f"✍️ Напишите свой ответ в чат."
        )
        keyboard = get_action_keyboard(task_type, level, next_index)
        await message.answer(message_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await state.clear()

# ---------- Показать пример ----------
@router.callback_query(F.data.startswith("writing_show_sample:"))
async def show_sample(callback: CallbackQuery, state: FSMContext):
    _, short_type, level, index_str = callback.data.split(":")
    index = int(index_str)
    data = await state.get_data()
    tasks = data.get("tasks", [])
    if not tasks or index >= len(tasks):
        await callback.answer("Пример не найден", show_alert=True)
        return
    task = tasks[index]
    sample = task.get("sample_answer", "Пример отсутствует")
    await callback.message.answer(f"📝 *Пример ответа:*\n\n{sample}", parse_mode="Markdown")
    await callback.answer()

# ---------- Отмена ----------
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