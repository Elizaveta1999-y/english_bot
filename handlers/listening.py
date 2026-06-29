import os
import json
import logging
import tempfile
import subprocess
import random
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from speaking.services.tts import text_to_voice
import redis.asyncio as redis

router = Router()
logger = logging.getLogger(__name__)

TASKS_FILE = "data/listening_tasks.json"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Загружаем все задания
with open(TASKS_FILE, "r", encoding="utf-8") as f:
    ALL_TASKS = json.load(f)

# Типы заданий (отображаемые названия)
TASK_TYPES = {
    "choice": "📝 Выбор варианта",
    "truefalse": "⚖️ True/False/Not stated",
    "fill_one": "📁 Вставка пропуска",
    "fill_multiple": "📄 Вставка пропусков",
    "speaker": "☑️ Выбор утверждения",
    "random": "🎲 Случайный тип"
}

LEVELS = {
    "beginner": "🌱 Новичок",
    "intermediate": "🌟 Любитель",
    "expert": "🚀 Эксперт"
}

redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

class ListeningState(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    answering_task = State()

def convert_to_opus(mp3_path: str) -> str:
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", "-ar", "16000", "-ac", "1", "-b:a", "16k", ogg_path, "-y"]
    subprocess.run(cmd, check=True, capture_output=True)
    return ogg_path

# ---------- Клавиатуры ----------
def get_types_keyboard():
    buttons = []
    for key, label in TASK_TYPES.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"listening_type_{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_levels_keyboard(task_type):
    buttons = []
    for level, label in LEVELS.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"listening_level_{task_type}_{level}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_types")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_choice_keyboard(options, task_id):
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"listening_answer_{task_id}_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_truefalse_keyboard(task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Верно", callback_data=f"listening_answer_{task_id}_true")],
        [InlineKeyboardButton(text="Неверно", callback_data=f"listening_answer_{task_id}_false")],
        [InlineKeyboardButton(text="Не сказано", callback_data=f"listening_answer_{task_id}_notstated")]
    ])

def get_task_control_keyboard(task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"listening_show_answer_{task_id}"),
            InlineKeyboardButton(text="Завершить", callback_data="listening_finish")
        ]
    ])

def get_finish_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Следующее задание", callback_data="listening_next_task"),
            InlineKeyboardButton(text="Завершить сессию", callback_data="listening_finish_session")
        ]
    ])

# ---------- Вспомогательные функции ----------
async def get_task_index(user_id: int, task_type: str, level: str) -> int:
    r = await get_redis()
    key = f"listening_progress:{user_id}:{task_type}:{level}"
    val = await r.get(key)
    return int(val) if val else 0

async def set_task_index(user_id: int, task_type: str, level: str, index: int):
    r = await get_redis()
    await r.set(f"listening_progress:{user_id}:{task_type}:{level}", str(index))

async def get_random_order(user_id: int, level: str) -> list:
    """Возвращает список ID заданий в случайном порядке для уровня (все типы)."""
    r = await get_redis()
    key = f"listening_random_order:{user_id}:{level}"
    order = await r.get(key)
    if order is None:
        # Генерируем новый порядок
        tasks = [t for t in ALL_TASKS if t.get("level") == level]
        random.shuffle(tasks)
        order = [t["id"] for t in tasks]
        await r.set(key, json.dumps(order))
    else:
        order = json.loads(order)
    return order

async def set_random_index(user_id: int, level: str, index: int):
    r = await get_redis()
    await r.set(f"listening_random_progress:{user_id}:{level}", str(index))

async def get_random_index(user_id: int, level: str) -> int:
    r = await get_redis()
    val = await r.get(f"listening_random_progress:{user_id}:{level}")
    return int(val) if val else 0

def get_tasks_by_type_and_level(task_type, level):
    return [t for t in ALL_TASKS if t.get("type") == task_type and t.get("level") == level]

def normalize_text_answer(answer: str) -> str:
    return ' '.join(answer.strip().lower().split())

# ---------- Отправка задания ----------
async def send_task(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data["task_type"]
    level = data["level"]
    user_id = message.from_user.id

    if task_type == "random":
        # Получаем случайный порядок
        order = await get_random_order(user_id, level)
        if not order:
            await message.answer("Нет заданий для этого уровня.")
            return
        index = await get_random_index(user_id, level)
        if index >= len(order):
            index = 0
            await set_random_index(user_id, level, 0)
        task_id = order[index]
        # Ищем задание по ID
        task = next((t for t in ALL_TASKS if t["id"] == task_id), None)
        if not task:
            await message.answer("Ошибка: задание не найдено.")
            return
        # Сохраняем реальный тип для отображения
        actual_type = task["type"]
        await state.update_data({"task": task, "task_index": index, "actual_type": actual_type, "answered": False})
    else:
        tasks = get_tasks_by_type_and_level(task_type, level)
        if not tasks:
            await message.answer("Заданий этого типа и уровня пока нет.")
            return
        index = await get_task_index(user_id, task_type, level)
        if index >= len(tasks):
            index = 0
        task = tasks[index]
        await state.update_data({"task": task, "task_index": index, "answered": False})

    # Генерация аудио
    status_msg = await message.answer("⏳ Генерирую аудио...")
    audio_path = await text_to_voice(task["audio_text"], voice_id="yM93hbw8Qtvdma2wCnJG")
    if audio_path and os.path.exists(audio_path):
        try:
            ogg_path = convert_to_opus(audio_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            audio_file = BufferedInputFile(audio_bytes, filename="audio.ogg")
            await message.answer_voice(audio_file)
            os.unlink(audio_path)
            os.unlink(ogg_path)
        except Exception as e:
            logger.error(f"Ошибка отправки аудио: {e}")
            await message.answer(f"Текст для прослушивания:\n\n{task['audio_text']}")
    else:
        await message.answer(f"Текст для прослушивания:\n\n{task['audio_text']}")
    await status_msg.delete()

    # Отправляем вопрос
    await show_question(message, state)

async def show_question(message: Message, state: FSMContext):
    data = await state.get_data()
    task = data["task"]
    task_type = task["type"]  # реальный тип задания
    task_id = task["id"]

    # Если случайный режим, показываем реальный тип
    if data.get("task_type") == "random":
        type_label = TASK_TYPES.get(task_type, task_type)
        await message.answer(f"🎲 Случайный режим\nТип задания: {type_label}\nПрослушайте аудио и выполните задание.")
    else:
        type_label = TASK_TYPES.get(task_type, task_type)
        await message.answer(f"Тип: {type_label}\nПрослушайте аудио и выполните задание.")

    # Формируем вопрос в зависимости от типа
    if task_type == "choice":
        text = f"{task['question']}\n\nВыберите вариант:"
        keyboard = get_choice_keyboard(task["options"], task_id)
    elif task_type == "truefalse":
        text = f"{task['statement']}\n\nВерно, неверно или не сказано?"
        keyboard = get_truefalse_keyboard(task_id)
    elif task_type == "fill_one":
        text = f"{task['question']}\n\nВведите пропущенное слово:"
        keyboard = get_task_control_keyboard(task_id)  # только кнопки управления
    elif task_type == "fill_multiple":
        text = f"{task['question']}\n\nВведите все пропущенные слова через точку с запятой (;), например: слово1; слово2; слово3"
        keyboard = get_task_control_keyboard(task_id)
    elif task_type == "speaker":
        text = f"{task['question']}\n\n{chr(10).join(task['options'])}\n\nВыберите правильный вариант:"
        keyboard = get_choice_keyboard(task["options"], task_id)
    else:
        return

    await message.answer(text, reply_markup=keyboard)
    await state.set_state(ListeningState.answering_task)

# ---------- Проверка ответов ----------
async def handle_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("answered", False):
        await message.answer("Вы уже ответили на это задание. Переходим к следующему.")
        await go_to_next_task(message, state)
        return

    task = data.get("task")
    if not task:
        await message.answer("Ошибка. Попробуйте начать заново.")
        return

    user_input = message.text.strip()
    if not user_input:
        await message.answer("Пожалуйста, введите ответ.")
        return

    task_type = task["type"]
    is_correct = False
    result_text = ""

    if task_type == "fill_one":
        correct = task["correct"]
        if normalize_text_answer(user_input) == normalize_text_answer(correct):
            is_correct = True
            result_text = "✅ Правильно!"
        else:
            result_text = f"❌ Неправильно. Правильный ответ: {correct}"
    elif task_type == "fill_multiple":
        user_answers = [normalize_text_answer(a) for a in user_input.split(';') if a.strip()]
        correct_answers = [normalize_text_answer(a) for a in task["answers"]]
        if len(user_answers) != len(correct_answers):
            result_text = f"❌ Количество ответов не совпадает. Ожидалось {len(correct_answers)} слов."
        else:
            all_correct = all(u == c for u, c in zip(user_answers, correct_answers))
            if all_correct:
                is_correct = True
                result_text = "✅ Правильно!"
            else:
                result_text = f"❌ Неправильно. Правильные ответы: {'; '.join(task['answers'])}"
    else:
        # Для кнопочных типов этот обработчик не вызывается
        return

    if is_correct:
        data["correct"] = data.get("correct", 0) + 1
    else:
        data["wrong"] = data.get("wrong", 0) + 1

    await message.answer(result_text)
    data["answered"] = True
    await state.update_data(data)
    await go_to_next_task(message, state)

async def go_to_next_task(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data["task_type"]
    level = data["level"]
    user_id = message.from_user.id

    if task_type == "random":
        # Для случайного режима увеличиваем индекс в порядке
        order = await get_random_order(user_id, level)
        if not order:
            await message.answer("Нет заданий.")
            return
        new_index = data.get("task_index", 0) + 1
        if new_index >= len(order):
            new_index = 0
        await set_random_index(user_id, level, new_index)
        await state.update_data({"task_index": new_index, "answered": False})
    else:
        tasks = get_tasks_by_type_and_level(task_type, level)
        new_index = data.get("task_index", 0) + 1
        if new_index >= len(tasks):
            new_index = 0
        await set_task_index(user_id, task_type, level, new_index)
        await state.update_data({"task_index": new_index, "answered": False})

    await send_task(message, state)

async def finish_session_and_show_stats(message: Message, state: FSMContext, show_stats: bool = True):
    data = await state.get_data()
    correct = data.get("correct", 0)
    wrong = data.get("wrong", 0)
    total = correct + wrong
    if show_stats:
        stats = f"Правильно: {correct}\nОшибок: {wrong}\nТочность: {correct/total*100:.1f}%" if total else "Вы не дали ни одного ответа."
        await message.answer(f"Сессия завершена!\n\n{stats}", reply_markup=get_finish_keyboard())
    else:
        await message.answer("Сессия завершена. Возвращаемся в главное меню.")
    await state.clear()

# ---------- Middleware для перехвата текстовых сообщений ----------
@router.message.outer_middleware()
async def listening_text_middleware(call: types.Message, event: types.Message, data: dict):
    state: FSMContext = data.get('state')
    if state:
        current_state = await state.get_state()
        if current_state == ListeningState.answering_task:
            await handle_answer(event, state)
            return
    return await call(event, data)

# ---------- Обработчики кнопок и команд ----------
@router.callback_query(F.data == "start_listening")
@router.message(Command("listening"))
async def listening_start(event, state: FSMContext):
    await state.clear()
    text = "🎧 <b>Аудирование</b>\nВыберите тип задания:"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=get_types_keyboard(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=get_types_keyboard(), parse_mode="HTML")
        await event.answer()

@router.callback_query(F.data.startswith("listening_type_"))
async def type_selected(callback: CallbackQuery, state: FSMContext):
    task_type = callback.data.split("_")[-1]
    await state.update_data({"task_type": task_type})
    text = f"Тип: {TASK_TYPES[task_type]}\n\nВыберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(task_type), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("listening_level_"))
async def level_selected(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    task_type = parts[2]
    level = parts[3]
    user_id = callback.from_user.id
    await state.update_data({"level": level})

    # Инициализируем счётчики
    data = await state.get_data()
    data["correct"] = 0
    data["wrong"] = 0
    await state.update_data(data)

    await callback.message.delete()
    await send_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data.startswith("listening_answer_"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("answered", False):
        await callback.answer("Вы уже ответили на это задание.", show_alert=True)
        return

    task = data.get("task")
    if not task:
        await callback.answer("Ошибка. Попробуйте начать заново.", show_alert=True)
        return

    task_id = task["id"]
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка.", show_alert=True)
        return
    answer_part = parts[2]  # индекс для choice/speaker или true/false/notstated

    is_correct = False
    result_text = ""

    if task["type"] == "choice" or task["type"] == "speaker":
        selected_index = int(answer_part)
        correct_index = task["correct"]
        is_correct = (selected_index == correct_index)
        if is_correct:
            result_text = "✅ Правильно!"
        else:
            result_text = f"❌ Неправильно. Правильный ответ: {task['options'][correct_index]}"
    elif task["type"] == "truefalse":
        user_answer = answer_part
        correct = task["correct"]  # "true", "false" или "notstated"
        is_correct = (user_answer == correct)
        if is_correct:
            result_text = "✅ Правильно!"
        else:
            correct_label = {"true": "Верно", "false": "Неверно", "notstated": "Не сказано"}.get(correct, correct)
            result_text = f"❌ Неправильно. Правильный ответ: {correct_label}"

    if is_correct:
        data["correct"] = data.get("correct", 0) + 1
    else:
        data["wrong"] = data.get("wrong", 0) + 1

    await callback.message.answer(result_text)
    data["answered"] = True
    await state.update_data(data)
    await callback.answer()

    # Переход к следующему заданию
    await go_to_next_task(callback.message, state)

@router.callback_query(F.data.startswith("listening_show_answer_"))
async def show_answer(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    task = data.get("task")
    if not task or task["id"] != task_id:
        await callback.answer("Это не текущее задание.", show_alert=True)
        return

    # Формируем правильный ответ
    if task["type"] == "choice" or task["type"] == "speaker":
        answer_text = task["options"][task["correct"]]
    elif task["type"] == "truefalse":
        correct = task["correct"]
        answer_text = {"true": "Верно", "false": "Неверно", "notstated": "Не сказано"}.get(correct, correct)
    elif task["type"] == "fill_one":
        answer_text = task["correct"]
    elif task["type"] == "fill_multiple":
        answer_text = "; ".join(task["answers"])
    else:
        answer_text = "Нет ответа"

    await callback.message.answer(f"Правильный ответ: {answer_text}")
    data["answered"] = True
    await state.update_data(data)
    await go_to_next_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "listening_finish")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    await finish_session_and_show_stats(callback.message, state, show_stats=True)
    await callback.answer()

@router.callback_query(F.data == "listening_next_task")
async def next_task(callback: CallbackQuery, state: FSMContext):
    # Просто перезапускаем отправку задания (с тем же типом и уровнем)
    await callback.message.delete()
    await send_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "listening_finish_session")
async def finish_session_from_block(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Сессия аудирования завершена. Возвращаемся в главное меню.")
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "🎧 <b>Аудирование</b>\nВыберите тип задания:"
    await callback.message.edit_text(text, reply_markup=get_types_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()