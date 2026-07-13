import json
import os
import tempfile
import re
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Voice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import redis.asyncio as redis
from services.deepseek_govorenie import check_govorenie
from services.whisper_utils import speech_to_text

router = Router()

# ---------- Загрузка заданий ----------
TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/govorenie_tasks.json")

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

ALL_TASKS = load_tasks()

# ---------- Redis ----------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

# Храним текущий id задания (не индекс)
async def get_current_task_id(user_id: int, task_type: str, level: str) -> int:
    r = await get_redis()
    key = f"govorenie_progress:{user_id}:{task_type}:{level}"
    val = await r.get(key)
    return int(val) if val else 0  # по умолчанию 0

async def set_current_task_id(user_id: int, task_type: str, level: str, task_id: int):
    r = await get_redis()
    key = f"govorenie_progress:{user_id}:{task_type}:{level}"
    await r.set(key, str(task_id))

async def add_session_result(user_id: int, task_type: str, level: str, feedback: str):
    r = await get_redis()
    key = f"govorenie_session:{user_id}:{task_type}:{level}"
    await r.rpush(key, feedback)

async def get_session_results(user_id: int, task_type: str, level: str):
    r = await get_redis()
    key = f"govorenie_session:{user_id}:{task_type}:{level}"
    return await r.lrange(key, 0, -1)

async def clear_session_results(user_id: int, task_type: str, level: str):
    r = await get_redis()
    key = f"govorenie_session:{user_id}:{task_type}:{level}"
    await r.delete(key)

# ---------- Состояния FSM ----------
class GovorenieStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_voice = State()

# ---------- Клавиатуры ----------
def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📖 Чтение вслух", callback_data="g_type_reading"),
            InlineKeyboardButton(text="⏱ Беглость (1 мин)", callback_data="g_type_fluency")
        ],
        [
            InlineKeyboardButton(text="🎤 Интервью", callback_data="g_type_interview"),
            InlineKeyboardButton(text="🎲 Случайный", callback_data="g_type_random")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ])

def get_levels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌱 Новичок", callback_data="g_level_beginner"),
            InlineKeyboardButton(text="🔥 Любитель", callback_data="g_level_intermediate")
        ],
        [
            InlineKeyboardButton(text="🧠 Эксперт", callback_data="g_level_advanced"),
            InlineKeyboardButton(text="🔙 Назад к типам", callback_data="back_to_types")
        ]
    ])

def get_action_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Пример", callback_data="g_show_sample"),
            InlineKeyboardButton(text="➡️ Следующее", callback_data="g_next_task")
        ],
        [
            InlineKeyboardButton(text="❌ Завершить", callback_data="g_finish")
        ]
    ])

# ---------- ВХОД В РЕЖИМ ----------
async def show_task_types(message: Message, edit: bool = False):
    text = (
        "🎤 *Режим Говорение*\n\n"
        "Выберите тип задания:\n"
        "📖 *Чтение вслух* – прочитайте текст чётко\n"
        "⏱ *Беглость* – говорите без остановок 60 секунд\n"
        "🎤 *Интервью* – ответьте на все вопросы одним сообщением\n"
        "🎲 *Случайный* – бот выберет сам"
    )
    keyboard = get_types_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ---------- Выбор типа ----------
@router.callback_query(F.data.startswith("g_type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_type = callback.data.split("_")[2]
    await state.update_data(task_type=task_type)
    await state.set_state(GovorenieStates.choosing_level)
    text = f"Вы выбрали тип: *{task_type.upper()}*.\nТеперь выберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

# ---------- Выбор уровня и выдача первого задания ----------
@router.callback_query(F.data.startswith("g_level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    level = callback.data.split("_")[2]
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")

    if task_type == "random":
        possible_types = ["reading", "fluency", "interview"]
        task_type = random.choice(possible_types)
        await state.update_data(task_type=task_type)

    tasks = ALL_TASKS.get(task_type, {}).get(level, [])
    if not tasks:
        await callback.message.edit_text(f"Заданий для {task_type} уровня {level} пока нет.")
        return

    # Очищаем предыдущие результаты сессии
    await clear_session_results(user_id, task_type, level)

    # Получаем сохранённый id задания (или 0)
    current_id = await get_current_task_id(user_id, task_type, level)

    # Ищем задание с этим id, если не находим – берём первое (id=0)
    current_task = next((t for t in tasks if t.get("id") == current_id), None)
    if current_task is None:
        current_task = tasks[0]
        current_id = current_task["id"]

    await state.update_data(
        task_type=task_type,
        level=level,
        tasks=tasks,
        current_task=current_task,
        current_id=current_id
    )

    await show_task(callback.message, state, edit=True)

# ---------- Показать задание ----------
async def show_task(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    tasks = data.get("tasks", [])
    if not task:
        await message.answer("Ошибка: задание не найдено.")
        return

    task_id = task.get("id", 0)
    total = len(tasks)
    # Номер задания = id+1 (так как id начинается с 0)
    task_number = task_id + 1

    if task_type == "reading":
        task_text = (
            f"Задание {task_number} из {total} (Чтение вслух)\n\n"
            f"{task.get('instruction', '')}\n\n"
            f"_{task['text']}_"
        )
    elif task_type == "fluency":
        task_text = (
            f"Задание {task_number} из {total} (Беглость)\n\n"
            f"{task.get('instruction', '')}\n\n"
            f"**{task['topic']}**"
        )
    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        task_text = (
            f"Задание {task_number} из {total} (Интервью)\n\n"
            f"{task.get('instruction', '')}\n\n"
            f"{questions}"
        )
    else:
        task_text = "Неизвестный тип задания."

    keyboard = get_action_keyboard()
    if edit:
        await message.edit_text(task_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(task_text, reply_markup=keyboard, parse_mode="Markdown")

    await state.set_state(GovorenieStates.waiting_voice)

# ---------- Обработка голосового сообщения ----------
@router.message(GovorenieStates.waiting_voice, F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])
    current_id = data.get("current_id", 0)

    if not task:
        await message.answer("Ошибка: задание не найдено. Начните заново.")
        await state.clear()
        return

    voice: Voice = message.voice
    duration = voice.duration

    # Проверки длительности
    if duration < 2:
        await message.answer("Слишком коротко! Скажите что-то внятное (минимум 2 секунды).")
        return
    if task_type == "fluency" and duration < 60:
        await message.answer(f"Вы говорили только {duration} секунд. Нужно не менее 60 секунд. Попробуйте ещё раз.")
        return
    if duration > 180:
        await message.answer("Слишком длинное сообщение (максимум 3 минуты). Сократите ответ.")
        return

    # Скачиваем файл
    file_id = voice.file_id
    file = await message.bot.get_file(file_id)
    file_path = file.file_path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        await message.bot.download_file(file_path, tmp.name)
        tmp_path = tmp.name

    # Распознаём через Whisper
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        user_text = await speech_to_text(tmp_path)
    except Exception:
        await message.answer("Не удалось распознать голос. Попробуйте говорить чётче.")
        os.unlink(tmp_path)
        return
    finally:
        os.unlink(tmp_path)

    if not user_text or len(user_text.strip()) < 3:
        await message.answer("Не удалось разобрать речь. Попробуйте говорить ближе к микрофону.")
        return

    # Фильтр стоп-слов
    stop_words_ru = ["ааа", "эээ", "м-м", "ну", "типа", "блин", "как бы", "это самое"]
    words = user_text.lower().split()
    if words:
        stop_count = sum(1 for w in words if w in stop_words_ru)
        if stop_count / len(words) > 0.3:
            await message.answer("Ваша речь содержит слишком много слов-паразитов. Постарайтесь говорить без них.")
            return

    # Для чтения вслух – проверяем соответствие тексту
    if task_type == "reading":
        clean_expected = re.sub(r'[^\w\s]', '', task['text']).lower().split()
        clean_user = re.sub(r'[^\w\s]', '', user_text).lower().split()
        common = set(clean_expected) & set(clean_user)
        if len(common) < max(3, len(clean_expected) * 0.3):
            await message.answer("Похоже, вы читаете не тот текст. Проверьте задание и попробуйте ещё раз.")
            return

    # Отправляем в ИИ для проверки
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        feedback = await check_govorenie(
            task=task,
            task_type=task_type,
            user_text=user_text,
            level=level,
            duration=duration
        )
    except Exception:
        await message.answer("Ошибка при обращении к ИИ. Попробуйте позже.")
        return

    # Сохраняем фидбек в сессию
    await add_session_result(user_id, task_type, level, feedback)

    await message.answer(f"Результат проверки:\n\n{feedback}", parse_mode="Markdown")

    # Переходим к следующему заданию
    await go_to_next_task(message, state, user_id, task_type, level, current_id, tasks)

# ---------- Переход к следующему заданию (по id) ----------
async def go_to_next_task(message: Message, state: FSMContext, user_id: int, task_type: str, level: str, current_id: int, tasks: list):
    # Ищем следующее задание с id = current_id + 1
    next_task = next((t for t in tasks if t.get("id") == current_id + 1), None)
    if next_task is None:
        # Если не нашли – начинаем с первого (id=0)
        next_task = tasks[0]
        await message.answer("Поздравляем! Вы прошли все задания этого типа. Начинаем заново.")

    # Сохраняем новый id в Redis
    await set_current_task_id(user_id, task_type, level, next_task["id"])

    await state.update_data(
        current_task=next_task,
        current_id=next_task["id"]
    )
    await show_task(message, state, edit=False)

# ---------- Кнопка "Следующее задание" ----------
@router.callback_query(F.data == "g_next_task")
async def next_task_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])
    current_id = data.get("current_id", 0)
    user_id = callback.from_user.id

    if not tasks:
        await callback.message.answer("Нет заданий.")
        return

    # Переходим к следующему
    next_task = next((t for t in tasks if t.get("id") == current_id + 1), None)
    if next_task is None:
        next_task = tasks[0]
        await callback.message.answer("Вы прошли все задания! Начинаем заново.")

    await set_current_task_id(user_id, task_type, level, next_task["id"])
    await state.update_data(
        current_task=next_task,
        current_id=next_task["id"]
    )
    await show_task(callback.message, state, edit=True)

# ---------- Кнопка "Пример" ----------
@router.callback_query(F.data == "g_show_sample")
async def show_sample_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task = data.get("current_task")
    if not task:
        await callback.message.answer("Задание не найдено.")
        return

    sample = task.get("sample", "Пример отсутствует.")
    await callback.message.answer(f"Пример ответа:\n\n{sample}")

# ---------- Кнопка "Завершить" ----------
@router.callback_query(F.data == "g_finish")
async def finish_govorenie(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")

    results = await get_session_results(user_id, task_type, level)
    count = len(results)

    if count == 0:
        summary = "Вы не выполнили ни одного задания."
    else:
        summary = f"✅ Вы выполнили {count} заданий.\n\n"
        last_feedbacks = results[-3:] if len(results) > 3 else results
        for i, fb in enumerate(last_feedbacks, start=max(1, count-2)):
            summary += f"--- Задание {i} ---\n{fb}\n\n"
        summary += "Отличная работа! Продолжайте практиковаться."

    await clear_session_results(user_id, task_type, level)
    await state.clear()

    await callback.message.answer(f"🏁 Режим говорения завершён.\n\n{summary}")
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

# ---------- Навигация ----------
@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(GovorenieStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_govorenie(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)