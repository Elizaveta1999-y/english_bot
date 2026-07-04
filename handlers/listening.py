import os
import json
import logging
import random
import time
from datetime import datetime
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import redis.asyncio as redis
from data.users import get_user_state, set_user_state  # <-- ДОБАВЛЕН ИМПОРТ

router = Router()
logger = logging.getLogger(__name__)

TASKS_FILE = "data/listening_tasks.json"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-c634646ded324b52b180b35da5c15a13.r2.dev/")

with open(TASKS_FILE, "r", encoding="utf-8") as f:
    ALL_TASKS = json.load(f)
    print(f"DEBUG: loaded {len(ALL_TASKS)} tasks")
    for t in ["fill_one", "fill_multiple"]:
        count = sum(1 for task in ALL_TASKS if task.get("type") == t)
        print(f"DEBUG: type '{t}' count = {count}")

TASK_TYPES = {
    "choice": "📝 Выбор варианта",
    "truefalse": "⚖️ True/False/Not stated",
    "fill_one": "📁 Вставка пропуска",
    "fill_multiple": "📄 Вставка пропусков",
    "speaker": "☑️ Выбор утверждения",
    "random": "🎲 Случайный тип"
}

TASK_TYPE_DESCRIPTIONS = {
    "choice": "выберите верный ответ на вопрос",
    "truefalse": "выберите верное утверждение",
    "fill_one": "введите пропущенное слово",
    "fill_multiple": "введите все пропущенные слова",
    "speaker": "выберите верное утверждение",
    "random": "выполните задание"
}

LEVELS = {
    "beginner": "🌱 Новичок",
    "intermediate": "📚 Любитель",
    "expert": "🎓 Эксперт"
}

WELCOME_MESSAGES = [
    "<b>🎧 Аудирование</b>\n\n<i>Умение понимать английскую речь на слух — ключевой навык для общения. Регулярная практика поможет привыкнуть к темпу, акцентам и живой интонации.</i>\n\nВыберите тип задания и уровень — и тренируйтесь в удобном темпе.",
    "<b>🎧 Аудирование</b>\n\n<i>Исследования показывают: 30 минут практики в день заметно улучшают понимание речи на слух уже через месяц. Ваш мозг привыкает быстрее, чем вы думаете.</i>\n\nГотовы начать?",
    "<b>🎧 Аудирование</b>\n\n<i>Тренируйте восприятие речи на слух. Выбирайте тип задания и уровень, отвечайте на вопросы — и следите за прогрессом.</i>\n\nПриступим?",
    "<b>🎧 Аудирование</b>\n\n<i>Говорят, что понять английскую речь сложно, только пока не привыкнешь. А привыкнуть можно только практикой.</i>\n\nВыбирайте задание, слушайте, отвечайте — и скоро начнете понимать больше обычного.",
    "<b>🎧 Аудирование</b>\n\n<i>Понимание речи на слух — навык, который развивается только практикой. Чем чаще вы слушаете, тем легче становится.</i>\n\nПопробуйте начать с коротких заданий — даже 5 минут в день дают результат."
]

redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

async def get_welcome_message():
    r = await get_redis()
    today = datetime.now().date().isoformat()
    saved_date = await r.get("listening_welcome_date")
    saved_index = await r.get("listening_welcome_index")
    if saved_date == today and saved_index is not None:
        index = int(saved_index)
    else:
        current_index = int(saved_index) if saved_index is not None else -1
        index = (current_index + 1) % len(WELCOME_MESSAGES)
        await r.set("listening_welcome_date", today)
        await r.set("listening_welcome_index", str(index))
    return WELCOME_MESSAGES[index]

class ListeningState(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    answering_task = State()
    revision_mode = State()

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
    buttons.append([
        InlineKeyboardButton(text="Показать ответ", callback_data=f"listening_show_answer_{task_id}"),
        InlineKeyboardButton(text="Завершить", callback_data="listening_finish")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_truefalse_keyboard(task_id):
    buttons = [
        [InlineKeyboardButton(text="True", callback_data=f"listening_answer_{task_id}_true")],
        [InlineKeyboardButton(text="False", callback_data=f"listening_answer_{task_id}_false")],
        [InlineKeyboardButton(text="Not stated", callback_data=f"listening_answer_{task_id}_notstated")]
    ]
    buttons.append([
        InlineKeyboardButton(text="Показать ответ", callback_data=f"listening_show_answer_{task_id}"),
        InlineKeyboardButton(text="Завершить", callback_data="listening_finish")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_fill_keyboard(task_id):
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

def get_progress_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📘 Работа над ошибками", callback_data="listening_revision")],
        [InlineKeyboardButton(text="🗑️ Сбросить прогресс", callback_data="listening_reset_progress")]
    ])

def get_revision_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Обратно к режиму", callback_data="listening_back_to_mode")],
        [InlineKeyboardButton(text="🗑️ Сбросить ошибки", callback_data="listening_reset_errors")]
    ])

# ---------- Работа с ошибками (Redis) ----------
async def add_error(user_id: int, task_type: str, level: str, task_id: int):
    r = await get_redis()
    key = f"listening_errors:{user_id}:{task_type}:{level}"
    await r.sadd(key, str(task_id))

async def remove_error(user_id: int, task_type: str, level: str, task_id: int):
    r = await get_redis()
    key = f"listening_errors:{user_id}:{task_type}:{level}"
    await r.srem(key, str(task_id))

async def get_errors(user_id: int, task_type: str, level: str) -> list:
    r = await get_redis()
    key = f"listening_errors:{user_id}:{task_type}:{level}"
    members = await r.smembers(key)
    return [int(m) for m in members]

async def clear_errors(user_id: int, task_type: str, level: str):
    r = await get_redis()
    key = f"listening_errors:{user_id}:{task_type}:{level}"
    await r.delete(key)

# ---------- Работа с прогрессом (Redis) ----------
async def get_correct(user_id: int, task_type: str, level: str) -> int:
    r = await get_redis()
    key = f"listening_correct:{user_id}:{task_type}:{level}"
    val = await r.get(key)
    return int(val) if val else 0

async def set_correct(user_id: int, task_type: str, level: str, count: int):
    r = await get_redis()
    key = f"listening_correct:{user_id}:{task_type}:{level}"
    await r.set(key, str(count))

async def get_wrong(user_id: int, task_type: str, level: str) -> int:
    r = await get_redis()
    key = f"listening_wrong:{user_id}:{task_type}:{level}"
    val = await r.get(key)
    return int(val) if val else 0

async def set_wrong(user_id: int, task_type: str, level: str, count: int):
    r = await get_redis()
    key = f"listening_wrong:{user_id}:{task_type}:{level}"
    await r.set(key, str(count))

async def clear_progress(user_id: int, task_type: str, level: str):
    r = await get_redis()
    await r.delete(f"listening_correct:{user_id}:{task_type}:{level}")
    await r.delete(f"listening_wrong:{user_id}:{task_type}:{level}")

# ---------- Основные функции ----------
async def get_task_index(user_id: int, task_type: str, level: str) -> int:
    r = await get_redis()
    key = f"listening_progress:{user_id}:{task_type}:{level}"
    val = await r.get(key)
    return int(val) if val else 0

async def set_task_index(user_id: int, task_type: str, level: str, index: int):
    r = await get_redis()
    await r.set(f"listening_progress:{user_id}:{task_type}:{level}", str(index))

async def get_random_order(user_id: int, level: str) -> list:
    r = await get_redis()
    key = f"listening_random_order:{user_id}:{level}"
    order = await r.get(key)
    if order is None:
        tasks = [t for t in ALL_TASKS if t.get("level") == level]
        if not tasks:
            return []
        random.shuffle(tasks)
        order = [t["id"] for t in tasks]
        await r.set(key, json.dumps(order))
    else:
        order = json.loads(order)
        if not order:
            tasks = [t for t in ALL_TASKS if t.get("level") == level]
            if not tasks:
                return []
            random.shuffle(tasks)
            order = [t["id"] for t in tasks]
            await r.set(key, json.dumps(order))
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
async def send_task(message: Message, state: FSMContext, is_revision=False, task_type=None, level=None):
    data = await state.get_data()
    if task_type is None:
        task_type = data["task_type"]
    if level is None:
        level = data["level"]
    user_id = message.from_user.id
    msg_ids = data.get("message_ids", [])

    if is_revision:
        error_ids = await get_errors(user_id, task_type, level)
        if not error_ids:
            msg = await message.answer("🎉 Ошибок нет! Вы всё исправили.")
            msg_ids.append(msg.message_id)
            await state.update_data({"message_ids": msg_ids})
            await state.set_state(ListeningState.choosing_type)
            # Сбрасываем флаг, так как выходим из режима исправления
            user_state = get_user_state(user_id)
            user_state["listening_active"] = False
            set_user_state(user_id, user_state)
            return
        task_id = error_ids[0]
        task = next((t for t in ALL_TASKS if t["id"] == task_id), None)
        if not task:
            await message.answer("Ошибка: задание не найдено.")
            return
        await state.update_data({"task": task, "answered": False, "is_revision": True})
    else:
        if task_type == "random":
            tasks_for_level = [t for t in ALL_TASKS if t.get("level") == level]
            print(f"DEBUG random: found {len(tasks_for_level)} tasks for level {level}")
            if not tasks_for_level:
                await message.answer(f"Нет заданий для уровня {level}.")
                return
            order = await get_random_order(user_id, level)
            if not order:
                msg = await message.answer("Нет заданий для этого уровня.")
                msg_ids.append(msg.message_id)
                await state.update_data({"message_ids": msg_ids})
                return
            index = await get_random_index(user_id, level)
            if index >= len(order):
                index = 0
                await set_random_index(user_id, level, 0)
            task_id = order[index]
            task = next((t for t in ALL_TASKS if t["id"] == task_id), None)
            if not task:
                await message.answer("Ошибка: задание не найдено.")
                return
            await state.update_data({"task": task, "task_index": index, "answered": False, "is_revision": False})
        else:
            tasks = get_tasks_by_type_and_level(task_type, level)
            if not tasks:
                msg = await message.answer("Заданий этого типа и уровня пока нет.")
                msg_ids.append(msg.message_id)
                await state.update_data({"message_ids": msg_ids})
                return
            index = await get_task_index(user_id, task_type, level)
            if index >= len(tasks):
                index = 0
                await set_task_index(user_id, task_type, level, 0)
            task = tasks[index]
            await state.update_data({"task": task, "task_index": index, "answered": False, "is_revision": False})

    filename = f"{task['level']}_{task['type']}_{task['id']}.mp3"
    audio_url = R2_PUBLIC_URL + filename + f"?v={int(time.time())}"
    try:
        msg = await message.answer_voice(audio_url)
        msg_ids.append(msg.message_id)
        await state.update_data({"message_ids": msg_ids})
    except Exception as e:
        logger.error(f"Ошибка отправки аудио: {e}")
        msg = await message.answer(f"Текст для прослушивания:\n\n{task['audio_text']}")
        msg_ids.append(msg.message_id)
        await state.update_data({"message_ids": msg_ids})

    await show_question(message, state)

async def show_question(message: Message, state: FSMContext):
    data = await state.get_data()
    task = data["task"]
    task_type = task["type"]
    task_id = task["id"]
    msg_ids = data.get("message_ids", [])

    if task_type == "choice":
        text = f"{task['question']}\n\nВыберите правильный вариант:"
        keyboard = get_choice_keyboard(task["options"], task_id)
    elif task_type == "truefalse":
        text = f"{task['statement']}\n\nВыберите верное утверждение:"
        keyboard = get_truefalse_keyboard(task_id)
    elif task_type == "fill_one":
        text = f"{task['question']}\n\nВведите пропущенное слово:"
        keyboard = get_fill_keyboard(task_id)
    elif task_type == "fill_multiple":
        text = f"{task['question']}\n\nВведите все пропущенные слова в формате: ___; ___; ___;"
        keyboard = get_fill_keyboard(task_id)
    elif task_type == "speaker":
        text = f"Выберите верное утверждение:"
        keyboard = get_choice_keyboard(task["options"], task_id)
    else:
        return

    msg = await message.answer(text, reply_markup=keyboard)
    msg_ids.append(msg.message_id)
    await state.update_data({"message_ids": msg_ids})
    await state.set_state(ListeningState.answering_task)

async def update_progress_message(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data["task_type"]
    correct = data.get("correct", 0)
    wrong = data.get("wrong", 0)
    progress_msg_id = data.get("progress_message_id")

    if progress_msg_id:
        text = (
            f"Режим: {TASK_TYPES[task_type]}\n\n"
            f"Внимательно прослушайте аудио и {TASK_TYPE_DESCRIPTIONS[task_type]}.\n\n"
            f"Ваш прогресс:\n"
            f"✔️ Правильно: {correct}\n"
            f"✖️ Ошибок: {wrong}\n\n"
            f"/revision_mode — работа над ошибками\n"
            f"/reset_progress — сбросить прогресс\n\n"
            f"Начинаем?"
        )
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg_id,
                text=text,
                reply_markup=get_progress_keyboard()
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить прогресс: {e}")

# ---------- Обработчики команд и кнопок ----------
@router.callback_query(F.data == "start_listening")
@router.message(Command("listening"))
async def listening_start(event, state: FSMContext):
    await state.clear()
    text = await get_welcome_message()
    if isinstance(event, Message):
        await event.answer(text, reply_markup=get_types_keyboard(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=get_types_keyboard(), parse_mode="HTML")
        await event.answer()

@router.callback_query(F.data.startswith("listening_type_"))
async def type_selected(callback: CallbackQuery, state: FSMContext):
    task_type = callback.data[len("listening_type_"):]
    if task_type == "one":
        task_type = "fill_one"
    elif task_type == "multiple":
        task_type = "fill_multiple"
    print(f"DEBUG: type_selected task_type={task_type}")
    await state.update_data({"task_type": task_type})
    text = "Выберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(task_type))
    await callback.answer()

@router.callback_query(F.data.startswith("listening_level_"))
async def level_selected(callback: CallbackQuery, state: FSMContext):
    rest = callback.data[len("listening_level_"):]
    parts = rest.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("Ошибка в данных.", show_alert=True)
        return
    task_type, level = parts[0], parts[1]
    if task_type == "one":
        task_type = "fill_one"
    elif task_type == "multiple":
        task_type = "fill_multiple"
    user_id = callback.from_user.id

    # === УСТАНАВЛИВАЕМ ФЛАГ, ЧТО МЫ В РЕЖИМЕ АУДИРОВАНИЯ ===
    user_state = get_user_state(user_id)
    user_state["listening_active"] = True
    set_user_state(user_id, user_state)

    if task_type == "random":
        tasks = [t for t in ALL_TASKS if t.get("level") == level]
    else:
        tasks = get_tasks_by_type_and_level(task_type, level)

    print(f"DEBUG: level_selected task_type={task_type}, level={level}, tasks={len(tasks)}")
    if not tasks:
        # Если нет заданий, сбрасываем флаг
        user_state = get_user_state(user_id)
        user_state["listening_active"] = False
        set_user_state(user_id, user_state)
        await callback.answer("Нет заданий для этого типа и уровня.", show_alert=True)
        return

    correct = await get_correct(user_id, task_type, level)
    wrong = await get_wrong(user_id, task_type, level)

    await state.update_data({
        "task_type": task_type,
        "level": level,
        "correct": correct,
        "wrong": wrong,
        "total": len(tasks),
        "index": 0,
        "message_ids": []
    })

    text = (
        f"Режим: {TASK_TYPES[task_type]}\n\n"
        f"Внимательно прослушайте аудио и {TASK_TYPE_DESCRIPTIONS[task_type]}.\n\n"
        f"Ваш прогресс:\n"
        f"✔️ Правильно: {correct}\n"
        f"✖️ Ошибок: {wrong}\n\n"
        f"/revision_mode — работа над ошибками\n"
        f"/reset_progress — сбросить прогресс\n\n"
        f"Начинаем?"
    )
    msg = await callback.message.answer(text, reply_markup=get_progress_keyboard())
    data = await state.get_data()
    msg_ids = data.get("message_ids", [])
    msg_ids.append(msg.message_id)
    await state.update_data({"message_ids": msg_ids, "progress_message_id": msg.message_id})
    await callback.message.delete()
    await send_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "listening_revision")
async def revision_mode(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = callback.from_user.id

    if not task_type or not level:
        await callback.answer("Сначала выберите тип и уровень в режиме аудирования.", show_alert=True)
        return

    # Устанавливаем флаг
    user_state = get_user_state(user_id)
    user_state["listening_active"] = True
    set_user_state(user_id, user_state)

    error_ids = await get_errors(user_id, task_type, level)
    count = len(error_ids)

    text = (
        f"📘 Работа над ошибками\n"
        f"Режим: {TASK_TYPES[task_type]}\n\n"
        f"Заданий на исправление: {count}"
    )
    await callback.message.edit_text(text, reply_markup=get_revision_keyboard())
    await state.set_state(ListeningState.revision_mode)

    if count == 0:
        msg = await callback.message.answer("🎉 Ошибок нет! Отличная работа.")
        data = await state.get_data()
        msg_ids = data.get("message_ids", [])
        msg_ids.append(msg.message_id)
        await state.update_data({"message_ids": msg_ids})
        # Сбрасываем флаг, так как ошибок нет, выходим из режима
        user_state = get_user_state(user_id)
        user_state["listening_active"] = False
        set_user_state(user_id, user_state)
    else:
        await send_task(callback.message, state, is_revision=True, task_type=task_type, level=level)
    await callback.answer()

@router.callback_query(F.data == "listening_reset_errors")
async def reset_errors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = callback.from_user.id

    if task_type and level:
        await clear_errors(user_id, task_type, level)
        await callback.answer("Все ошибки сброшены.")
        await callback.message.edit_text(
            f"📘 Работа над ошибками\nРежим: {TASK_TYPES[task_type]}\n\nЗаданий на исправление: 0"
        )
        # Сбрасываем флаг, выходим из режима
        user_state = get_user_state(user_id)
        user_state["listening_active"] = False
        set_user_state(user_id, user_state)
    else:
        await callback.answer("Ошибка: не удалось сбросить.")

@router.callback_query(F.data == "listening_back_to_mode")
async def back_to_mode(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_ids = data.get("message_ids", [])
    chat_id = callback.message.chat.id

    for mid in msg_ids:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass

    await state.set_state(ListeningState.choosing_level)
    task_type = data.get("task_type")
    level = data.get("level")
    if task_type and level:
        correct = data.get("correct", 0)
        wrong = data.get("wrong", 0)
        text = (
            f"Режим: {TASK_TYPES[task_type]}\n\n"
            f"Внимательно прослушайте аудио и {TASK_TYPE_DESCRIPTIONS[task_type]}.\n\n"
            f"Ваш прогресс:\n"
            f"✔️ Правильно: {correct}\n"
            f"✖️ Ошибок: {wrong}\n\n"
            f"/revision_mode — работа над ошибками\n"
            f"/reset_progress — сбросить прогресс\n\n"
            f"Начинаем?"
        )
        msg = await callback.message.answer(text, reply_markup=get_progress_keyboard())
        new_msg_ids = [msg.message_id]
        await state.update_data({"message_ids": new_msg_ids, "progress_message_id": msg.message_id})
        await callback.message.delete()
        # Флаг уже установлен, не сбрасываем
        await send_task(callback.message, state)
    else:
        await callback.answer("Ошибка: режим не найден.")
        # Сбрасываем флаг, так как выходим
        user_id = callback.from_user.id
        user_state = get_user_state(user_id)
        user_state["listening_active"] = False
        set_user_state(user_id, user_state)
    await callback.answer()

@router.callback_query(F.data == "listening_reset_progress")
async def reset_progress(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = callback.from_user.id

    if not task_type or not level:
        await callback.answer("Ошибка: не удалось определить режим. Выберите тип и уровень заново.", show_alert=True)
        return

    msg_ids = data.get("message_ids", [])
    chat_id = callback.message.chat.id
    for mid in msg_ids:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass

    await set_task_index(user_id, task_type, level, 0)
    await clear_progress(user_id, task_type, level)
    await state.update_data({
        "correct": 0,
        "wrong": 0,
        "index": 0,
        "message_ids": []
    })

    await update_progress_message(callback.message, state)
    await callback.answer("Прогресс сброшен. Начинаем с первого задания.")
    # Флаг уже установлен, не сбрасываем
    await send_task(callback.message, state)

# ---------- Обработка ответов ----------
@router.callback_query(F.data.startswith("listening_answer_"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("answered", False):
        await callback.answer("Вы уже ответили на это задание.", show_alert=True)
        return

    task = data.get("task")
    if not task:
        await callback.answer("Ошибка.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка.", show_alert=True)
        return
    answer_part = parts[3]

    is_correct = False
    result_text = ""

    if task["type"] in ["choice", "speaker"]:
        selected_index = int(answer_part)
        correct_index = int(task["correct"])
        is_correct = (selected_index == correct_index)
        if is_correct:
            result_text = "Правильно!"
        else:
            result_text = f"Неправильно. Правильный ответ: {task['options'][correct_index]}"
    elif task["type"] == "truefalse":
        user_answer = answer_part
        correct = task["correct"]
        is_correct = (user_answer == correct)
        if is_correct:
            result_text = "Правильно!"
        else:
            correct_label = {"true": "True", "false": "False", "notstated": "Not stated"}.get(correct, correct)
            result_text = f"Неправильно. Правильный ответ: {correct_label}"
    else:
        return

    if is_correct:
        data["correct"] = data.get("correct", 0) + 1
        await set_correct(callback.from_user.id, data["task_type"], data["level"], data["correct"])
        if data.get("is_revision", False):
            await remove_error(callback.from_user.id, data["task_type"], data["level"], task["id"])
    else:
        data["wrong"] = data.get("wrong", 0) + 1
        await set_wrong(callback.from_user.id, data["task_type"], data["level"], data["wrong"])
        if not data.get("is_revision", False):
            await add_error(callback.from_user.id, data["task_type"], data["level"], task["id"])

    await callback.message.edit_text(callback.message.text, reply_markup=None)
    msg = await callback.message.answer(result_text)
    msg_ids = data.get("message_ids", [])
    msg_ids.append(msg.message_id)
    data["answered"] = True
    await state.update_data({"message_ids": msg_ids, **data})
    await callback.answer()
    await go_to_next_task(callback.message, state)

@router.callback_query(F.data.startswith("listening_show_answer_"))
async def show_answer(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split("_")[-1])
        data = await state.get_data()
        task = data.get("task")
        if not task or task["id"] != task_id:
            await callback.answer("Это не текущее задание.", show_alert=True)
            return

        if task["type"] in ["choice", "speaker"]:
            correct_index = int(task["correct"])
            answer_text = task["options"][correct_index]
        elif task["type"] == "truefalse":
            correct = task["correct"]
            answer_text = {"true": "True", "false": "False", "notstated": "Not stated"}.get(correct, correct)
        elif task["type"] == "fill_one":
            answer_text = task["correct"]
        elif task["type"] == "fill_multiple":
            answer_text = "; ".join(task["answers"])
        else:
            answer_text = ""

        await callback.message.edit_reply_markup(reply_markup=None)
        msg = await callback.message.answer(f"✅ Правильный ответ: {answer_text}")

        data = await state.get_data()
        msg_ids = data.get("message_ids", [])
        msg_ids.append(msg.message_id)
        await state.update_data({"message_ids": msg_ids})

        data["answered"] = True
        await state.update_data(data)
        await callback.answer()
        await go_to_next_task(callback.message, state)
    except Exception as e:
        logger.error(f"Ошибка в show_answer: {e}")
        await callback.answer("Произошла ошибка при показе ответа.", show_alert=True)

# ---------- Middleware ----------
@router.message.outer_middleware()
async def listening_text_middleware(call: types.Message, event: types.Message, data: dict):
    state: FSMContext = data.get('state')
    if state:
        current_state = await state.get_state()
        if current_state and current_state.startswith("ListeningState"):
            if event.text and event.text.startswith("/"):
                return await call(event, data)
            if current_state == ListeningState.answering_task:
                await handle_answer(event, state)
                return
            # Для всех других состояний ListeningState блокируем текст
            return
    return await call(event, data)

# ---------- Обработчики текстовых ответов (для fill_one/fill_multiple) ----------
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
            result_text = "Правильно!"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct}"
    elif task_type == "fill_multiple":
        user_answers = [normalize_text_answer(a) for a in user_input.split(';') if a.strip()]
        correct_answers = [normalize_text_answer(a) for a in task["answers"]]
        if len(user_answers) != len(correct_answers):
            result_text = f"Количество ответов не совпадает. Ожидалось {len(correct_answers)} слов."
        else:
            all_correct = all(u == c for u, c in zip(user_answers, correct_answers))
            if all_correct:
                is_correct = True
                result_text = "Правильно!"
            else:
                result_text = f"Неправильно. Правильные ответы: {'; '.join(task['answers'])}"
    else:
        return

    if is_correct:
        data["correct"] = data.get("correct", 0) + 1
        await set_correct(message.from_user.id, data["task_type"], data["level"], data["correct"])
        if data.get("is_revision", False):
            await remove_error(message.from_user.id, data["task_type"], data["level"], task["id"])
    else:
        data["wrong"] = data.get("wrong", 0) + 1
        await set_wrong(message.from_user.id, data["task_type"], data["level"], data["wrong"])
        if not data.get("is_revision", False):
            await add_error(message.from_user.id, data["task_type"], data["level"], task["id"])

    msg = await message.answer(result_text)
    msg_ids = data.get("message_ids", [])
    msg_ids.append(msg.message_id)
    data["answered"] = True
    await state.update_data({"message_ids": msg_ids, **data})
    await go_to_next_task(message, state)

async def go_to_next_task(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data["task_type"]
    level = data["level"]
    user_id = message.from_user.id

    if data.get("is_revision", False):
        await send_task(message, state, is_revision=True, task_type=task_type, level=level)
        return

    if task_type == "random":
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

# ---------- Прочие обработчики ----------
@router.callback_query(F.data == "listening_finish")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    correct = data.get("correct", 0)
    wrong = data.get("wrong", 0)
    total = correct + wrong
    msg_ids = data.get("message_ids", [])
    chat_id = callback.message.chat.id

    for mid in msg_ids:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass

    stats = f"Правильно: {correct}\nОшибок: {wrong}\nТочность: {correct/total*100:.1f}%" if total else "Вы не ответили ни на одно задание."
    await callback.message.answer(f"Сессия завершена!\n\n{stats}", reply_markup=get_finish_keyboard())
    # Сбрасываем флаг
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["listening_active"] = False
    set_user_state(user_id, user_state)
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "listening_next_task")
async def next_task(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await send_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "listening_finish_session")
async def finish_session_from_block(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_ids = data.get("message_ids", [])
    chat_id = callback.message.chat.id

    for mid in msg_ids:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass

    await state.clear()
    # Сбрасываем флаг
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["listening_active"] = False
    set_user_state(user_id, user_state)
    await callback.message.edit_text("Сессия завершена. Возвращаемся в главное меню.")
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_ids = data.get("message_ids", [])
    chat_id = callback.message.chat.id

    for mid in msg_ids:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass

    await state.clear()
    # Сбрасываем флаг
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["listening_active"] = False
    set_user_state(user_id, user_state)
    await callback.message.edit_text("🎧 Аудирование\nВыберите тип задания:", reply_markup=get_types_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_ids = data.get("message_ids", [])
    chat_id = callback.message.chat.id

    for mid in msg_ids:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass

    await state.clear()
    # Сбрасываем флаг
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["listening_active"] = False
    set_user_state(user_id, user_state)
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

# ---------- Обработчики команд ----------
@router.message(Command("revision_mode"))
async def revision_mode_command(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = message.from_user.id

    if not task_type or not level:
        await message.answer("Сначала выберите тип и уровень в режиме аудирования.")
        return

    # Устанавливаем флаг
    user_state = get_user_state(user_id)
    user_state["listening_active"] = True
    set_user_state(user_id, user_state)

    error_ids = await get_errors(user_id, task_type, level)
    count = len(error_ids)

    text = (
        f"📘 Работа над ошибками\n"
        f"Режим: {TASK_TYPES[task_type]}\n\n"
        f"Заданий на исправление: {count}"
    )
    await message.answer(text, reply_markup=get_revision_keyboard())
    await state.set_state(ListeningState.revision_mode)

    if count == 0:
        await message.answer("🎉 Ошибок нет! Отличная работа.")
        # Сбрасываем флаг, так как ошибок нет
        user_state = get_user_state(user_id)
        user_state["listening_active"] = False
        set_user_state(user_id, user_state)
    else:
        await send_task(message, state, is_revision=True, task_type=task_type, level=level)


@router.message(Command("debug_tasks"))
async def debug_tasks(message: Message):
    total = len(ALL_TASKS)
    fill_one = sum(1 for t in ALL_TASKS if t.get("type") == "fill_one")
    fill_multiple = sum(1 for t in ALL_TASKS if t.get("type") == "fill_multiple")
    await message.answer(f"Total: {total}\nfill_one: {fill_one}\nfill_multiple: {fill_multiple}")


@router.message(Command("debug_fill"))
async def debug_fill(message: Message):
    result = []
    for level in ["beginner", "intermediate", "expert"]:
        for t in ["fill_one", "fill_multiple"]:
            count = sum(1 for task in ALL_TASKS if task.get("type") == t and task.get("level") == level)
            result.append(f"{level} {t}: {count}")
    await message.answer("\n".join(result))


@router.message(Command("reset_progress"))
async def reset_progress_command(message: Message, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = message.from_user.id

    if not task_type or not level:
        await message.answer("Ошибка: не удалось определить режим. Выберите тип и уровень заново.")
        return

    await set_task_index(user_id, task_type, level, 0)
    await clear_progress(user_id, task_type, level)
    await state.update_data({"correct": 0, "wrong": 0, "index": 0, "message_ids": []})
    await message.answer("Прогресс сброшен. Начинаем с первого задания.")
    await send_task(message, state)


@router.message(Command("debug_get"))
async def debug_get(message: Message):
    result = []
    for level in ["beginner", "intermediate", "expert"]:
        for t in ["fill_one", "fill_multiple"]:
            tasks = get_tasks_by_type_and_level(t, level)
            result.append(f"{level} {t}: {len(tasks)}")
    await message.answer("\n".join(result))