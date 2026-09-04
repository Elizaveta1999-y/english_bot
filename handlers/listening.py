import os
import json
import logging
import time
import random
import hashlib
from aiogram import Router, F, types, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from data.users import get_user_state, set_user_state
from utils.db import (
    get_user_stats_db,
    update_user_stats_db,
    reset_user_stats_db,
    add_reading_error_db,
    remove_reading_error_db,
    get_reading_errors_db,
    clear_reading_errors_db,
    get_progress_index,
    set_progress_index,
    reset_progress_index,
    get_random_order,
    set_random_order,
    get_order_hash,
    set_order_hash,
    get_connection,
)

router = Router()
logger = logging.getLogger(__name__)

TASKS_FILE = "data/listening_tasks.json"
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-c634646ded324b52b180b35da5c15a13.r2.dev/")

with open(TASKS_FILE, "r", encoding="utf-8") as f:
    ALL_TASKS = json.load(f)

TASK_TYPES = {
    "choice": "📝 Выбор варианта",
    "truefalse": "⚖️ True/False/Not stated",
    "fill_one": "📁 Вставка пропуска",
    "fill_multiple": "📄 Вставка пропусков",
    "speaker": "☑️ Выбор утверждения",
}

LEVELS = {
    "beginner": "🌱 Новичок",
    "intermediate": "📚 Любитель",
    "expert": "🎓 Эксперт"
}

class ListeningState(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    answering_task = State()
    revision_mode = State()
    confirm_reset = State()
    confirm_reset_errors = State()

user_message_ids = {}

def ensure_list_of_ints(data):
    if isinstance(data, list):
        if all(isinstance(i, int) for i in data):
            return data
        else:
            try:
                return [int(i) for i in data]
            except:
                pass
    elif isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return ensure_list_of_ints(parsed)
        except:
            pass
        try:
            return [int(x.strip()) for x in data.split(',') if x.strip()]
        except:
            pass
    return []

async def clear_user_buttons(user_id, bot, chat_id):
    if user_id not in user_message_ids:
        return
    for msg_id in user_message_ids[user_id][:]:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
        except Exception as e:
            if "message to edit not found" in str(e).lower() or "message not found" in str(e).lower():
                pass
            else:
                logger.warning(f"Ошибка у msg_id={msg_id}: {e}")
        if msg_id in user_message_ids[user_id]:
            user_message_ids[user_id].remove(msg_id)
    user_message_ids[user_id] = []

def add_user_message(user_id, msg_id):
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg_id)

def get_types_keyboard():
    buttons = []
    for key, label in TASK_TYPES.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"listening_type_{key}")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="listening_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_levels_keyboard(task_type):
    buttons = []
    for level, label in LEVELS.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"listening_level_{task_type}_{level}")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="listening_back_to_types")])
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

def get_progress_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="listening_revision")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="listening_reset_progress")]
    ])

def get_revision_info_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Учебный режим", callback_data="revision_back_to_study")],
        [InlineKeyboardButton(text="Сбросить ошибки", callback_data="revision_reset_errors")]
    ])

def get_revision_card_keyboard(task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"listening_show_answer_{task_id}"),
            InlineKeyboardButton(text="Завершить", callback_data="revision_finish_card")
        ]
    ])

def get_confirm_reset_progress_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить", callback_data="confirm_reset_progress_yes")],
        [InlineKeyboardButton(text="Назад", callback_data="confirm_reset_progress_no")]
    ])

def get_confirm_reset_errors_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить ошибки", callback_data="confirm_reset_errors_yes")],
        [InlineKeyboardButton(text="Назад", callback_data="confirm_reset_errors_no")]
    ])

def make_listening_type_key(task_type: str) -> str:
    return f"listening_{task_type}"

def get_order_key(task_type: str, level: str) -> str:
    return f"listening_{task_type}_{level}"

def get_tasks_by_type_and_level(task_type, level):
    return [t for t in ALL_TASKS if t.get("type") == task_type and t.get("level") == level]

def normalize_text_answer(answer: str) -> str:
    return ' '.join(answer.strip().lower().split())

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
async def send_task(message, state, is_revision=False, task_type=None, level=None, error_ids=None, user_id=None):
    data = await state.get_data()
    if task_type is None:
        task_type = data["task_type"]
    if level is None:
        level = data["level"]
    if user_id is None:
        user_id = data.get("user_id") or message.from_user.id
    chat_id = message.chat.id

    question_msg_id = data.get("question_message_id")
    if question_msg_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=chat_id, message_id=question_msg_id, reply_markup=None)
        except:
            pass
        await state.update_data({"question_message_id": None})

    if is_revision:
        if error_ids is None:
            error_ids = await get_reading_errors_db(user_id, make_listening_type_key(task_type), level)
        if not error_ids:
            await message.answer("🎉 Ошибок нет. Отличная работа!")
            await exit_revision(message, state, show_progress=True, user_id=user_id)
            return
        task_id = error_ids[0]
        task = next((t for t in ALL_TASKS if t["id"] == task_id), None)
        if not task:
            await message.answer("Ошибка: задание не найдено.")
            return
        await state.update_data({"task": task, "answered": False, "is_revision": True})
    else:
        tasks = get_tasks_by_type_and_level(task_type, level)
        if not tasks:
            msg = await message.answer("Заданий этого типа и уровня пока нет.")
            add_user_message(user_id, msg.message_id)
            return

        order_key = get_order_key(task_type, level)
        shuffled_order = await get_random_order(user_id, order_key)
        
        if shuffled_order is None:
            content_str = json.dumps(tasks, sort_keys=True, ensure_ascii=False)
            current_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
            saved_hash = await get_order_hash(user_id, order_key)
            
            if saved_hash is None or saved_hash != current_hash:
                order = list(range(len(tasks)))
                random.shuffle(order)
                shuffled_order = order
                await set_random_order(user_id, order_key, shuffled_order)
                await set_order_hash(user_id, order_key, current_hash)
                await reset_progress_index(user_id, make_listening_type_key(task_type), level)
                logger.info(f"Задания {order_key} изменились, создан новый порядок, хеш={current_hash[:8]}...")
            else:
                shuffled_order = await get_random_order(user_id, order_key)
                if shuffled_order is None:
                    order = list(range(len(tasks)))
                    random.shuffle(order)
                    shuffled_order = order
                    await set_random_order(user_id, order_key, shuffled_order)
                    await set_order_hash(user_id, order_key, current_hash)
            
            shuffled_order = ensure_list_of_ints(shuffled_order)

        if not isinstance(shuffled_order, list) or not shuffled_order:
            logger.warning(f"Некорректный shuffled_order для {order_key}: {shuffled_order}, пересоздаём")
            order = list(range(len(tasks)))
            random.shuffle(order)
            shuffled_order = order
            await set_random_order(user_id, order_key, shuffled_order)

        index = await get_progress_index(user_id, make_listening_type_key(task_type), level)
        if index >= len(shuffled_order):
            index = 0
            await set_progress_index(user_id, make_listening_type_key(task_type), level, 0)
        task = tasks[shuffled_order[index]]
        await state.update_data({"task": task, "task_index": index, "answered": False, "is_revision": False})

    filename = f"{task['level']}_{task['type']}_{task['id']}.mp3"
    audio_url = R2_PUBLIC_URL + filename + f"?v={int(time.time())}"
    try:
        msg = await message.answer_voice(audio_url)
        add_user_message(user_id, msg.message_id)
    except Exception as e:
        logger.warning(f"Ошибка аудио: {e}")
        msg = await message.answer(f"Текст: {task['audio_text']}")
        add_user_message(user_id, msg.message_id)

    await show_question(message, state, is_revision=is_revision, user_id=user_id)

async def show_question(message, state, is_revision=False, user_id=None):
    data = await state.get_data()
    task = data["task"]
    task_type = task["type"]
    task_id = task["id"]
    if user_id is None:
        user_id = data.get("user_id") or message.from_user.id

    if task_type == "choice":
        text = f"{task['question']}\n\nВыберите вариант:"
        keyboard = get_choice_keyboard(task["options"], task_id)
    elif task_type == "truefalse":
        text = f"{task['statement']}\n\nВыберите:"
        keyboard = get_truefalse_keyboard(task_id)
    elif task_type == "fill_one":
        text = f"{task['question']}\n\nВведите ответ:"
        keyboard = get_fill_keyboard(task_id)
    elif task_type == "fill_multiple":
        text = f"{task['question']}\n\nВведите все ответы через ;"
        keyboard = get_fill_keyboard(task_id)
    elif task_type == "speaker":
        text = f"Выберите:"
        keyboard = get_choice_keyboard(task["options"], task_id)
    else:
        return

    if is_revision:
        keyboard = get_revision_card_keyboard(task_id)

    msg = await message.answer(text, reply_markup=keyboard)
    add_user_message(user_id, msg.message_id)
    await state.update_data({"question_message_id": msg.message_id})
    if is_revision:
        await state.update_data({"revision_card_msg_id": msg.message_id})
    await state.set_state(ListeningState.answering_task if not is_revision else ListeningState.revision_mode)

async def update_progress_message(message, state, reset=False, user_id=None):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    if not task_type or not level:
        return
    if user_id is None:
        user_id = data.get("user_id") or message.from_user.id
    error_ids = await get_reading_errors_db(user_id, make_listening_type_key(task_type), level)
    errors_count = len(error_ids)
    progress_msg_id = data.get("progress_message_id")
    chat_id = message.chat.id

    level_label = LEVELS.get(level, level)
    correct, wrong = await get_user_stats_db(user_id, make_listening_type_key(task_type), level)
    text = (
        f"Режим: {TASK_TYPES[task_type]}\n"
        f"Уровень: {level_label}\n\n"
        f"Внимательно прослушайте и выполните задание.\n\n"
        f"Ваш прогресс:\n"
        f"✔️ Правильно: {correct}\n"
        f"✖️ Ошибок: {errors_count}"
    )

    if progress_msg_id and not reset:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg_id,
                text=text,
                reply_markup=get_progress_keyboard()
            )
            return
        except Exception as e:
            if "message is not modified" not in str(e):
                logger.warning(f"Ошибка обновления прогресса: {e}")

    msg = await message.answer(text, reply_markup=get_progress_keyboard())
    add_user_message(user_id, msg.message_id)
    await state.update_data({"progress_message_id": msg.message_id})

async def exit_revision(message, state, show_progress=True, user_id=None):
    data = await state.get_data()
    if user_id is None:
        user_id = data.get("user_id") or message.from_user.id
    chat_id = message.chat.id

    info_msg_id = data.get("revision_info_msg_id")
    if info_msg_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=chat_id, message_id=info_msg_id, reply_markup=None)
        except:
            pass

    card_msg_id = data.get("revision_card_msg_id")
    if card_msg_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=chat_id, message_id=card_msg_id, reply_markup=None)
        except:
            pass

    await state.update_data({
        "is_revision": False,
        "revision_info_msg_id": None,
        "revision_card_msg_id": None,
        "answered": False,
        "task": None,
        "question_message_id": None
    })
    await state.set_state(ListeningState.answering_task)

    if show_progress:
        await update_progress_message(message, state, user_id=user_id)
        await send_task(message, state, user_id=user_id)

async def finish_revision_with_summary(message, state, user_id=None):
    data = await state.get_data()
    if user_id is None:
        user_id = data.get("user_id") or message.from_user.id
    fixed = data.get("revision_fixed", 0)
    total = data.get("revision_total", 0)

    if fixed == 0:
        summary = "Вы не исправили ни одной ошибки."
    elif fixed == total:
        summary = f"Вы исправили все ошибки! 🎉"
    else:
        remaining = total - fixed
        summary = f"Вы исправили: {fixed} из {total}\nОсталось ошибок: {remaining}"

    info_msg_id = data.get("revision_info_msg_id")
    if info_msg_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=info_msg_id, reply_markup=None)
        except:
            pass
    card_msg_id = data.get("revision_card_msg_id")
    if card_msg_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=card_msg_id, reply_markup=None)
        except:
            pass

    await message.answer(f"Работа над ошибками завершена.\n{summary}")
    await exit_revision(message, state, show_progress=True, user_id=user_id)

async def go_to_next_task(message, state, user_id=None):
    data = await state.get_data()
    if data.get("is_revision", False):
        return
    if user_id is None:
        user_id = data.get("user_id") or message.from_user.id

    task_type = data["task_type"]
    level = data["level"]
    order_key = get_order_key(task_type, level)
    shuffled_order = await get_random_order(user_id, order_key)
    if shuffled_order is None:
        tasks = get_tasks_by_type_and_level(task_type, level)
        order = list(range(len(tasks)))
        random.shuffle(order)
        shuffled_order = order
        await set_random_order(user_id, order_key, shuffled_order)
    shuffled_order = ensure_list_of_ints(shuffled_order)

    question_msg_id = data.get("question_message_id")
    if question_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=question_msg_id,
                reply_markup=None
            )
        except:
            pass
        await state.update_data({"question_message_id": None})

    tasks = get_tasks_by_type_and_level(task_type, level)
    new_index = data.get("task_index", 0) + 1
    if new_index >= len(shuffled_order):
        new_index = 0
    await set_progress_index(user_id, make_listening_type_key(task_type), level, new_index)
    await state.update_data({"task_index": new_index, "answered": False})
    await send_task(message, state, user_id=user_id)

async def go_to_next_revision(message, state, user_id=None):
    data = await state.get_data()
    if user_id is None:
        user_id = data.get("user_id") or message.from_user.id
    error_ids = data.get("revision_error_ids", [])
    index = data.get("revision_index", 0)
    fixed = data.get("revision_fixed", 0)
    total = data.get("revision_total", len(error_ids))

    question_msg_id = data.get("question_message_id")
    if question_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=question_msg_id,
                reply_markup=None
            )
        except:
            pass
        await state.update_data({"question_message_id": None})

    index += 1
    if index >= total:
        await finish_revision_with_summary(message, state, user_id=user_id)
        return

    await state.update_data({"revision_index": index, "answered": False, "task": None})
    await send_task(message, state, is_revision=True, error_ids=error_ids, user_id=user_id)

# ========== ПЕРЕХВАТ КОМАНД ==========
@router.message(
    F.text.startswith('/'),
    StateFilter(
        ListeningState.choosing_type,
        ListeningState.choosing_level,
        ListeningState.answering_task,
        ListeningState.revision_mode,
        ListeningState.confirm_reset,
        ListeningState.confirm_reset_errors
    )
)
async def handle_commands_in_listening(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"[CMD] Команда {message.text} в аудировании, user={message.from_user.id}")
    data = await state.get_data()
    user_id = data.get("user_id") or message.from_user.id
    chat_id = message.chat.id

    msg_ids = []
    for key in ["progress_message_id", "question_message_id", "revision_info_msg_id", "revision_card_msg_id"]:
        msg_id = data.get(key)
        if msg_id:
            msg_ids.append(msg_id)

    for msg_id in msg_ids:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
        except Exception as e:
            logger.warning(f"Ошибка у {msg_id}: {e}")

    await clear_user_buttons(user_id, bot, chat_id)
    await message.answer("Практика завершена.")
    await state.clear()
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    from .start import show_main_menu
    await show_main_menu(message, edit=False)

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@router.callback_query(F.data == "start_listening")
@router.message(Command("listening"))
async def listening_start(event, state: FSMContext):
    user_id = event.from_user.id
    chat_id = event.chat.id if hasattr(event, 'chat') else event.message.chat.id
    await clear_user_buttons(user_id, event.bot, chat_id)
    await state.clear()
    await state.set_state(ListeningState.choosing_type)
    await state.update_data({"user_id": user_id})
    text = "Аудирование 🎧\n\nВыберите режим:"
    if isinstance(event, Message):
        msg = await event.answer(text, reply_markup=get_types_keyboard(), parse_mode="HTML")
    else:
        msg = await event.message.edit_text(text, reply_markup=get_types_keyboard(), parse_mode="HTML")
        await event.answer()
    add_user_message(user_id, msg.message_id)

@router.callback_query(ListeningState.choosing_type, F.data.startswith("listening_type_"))
async def type_selected(callback: CallbackQuery, state: FSMContext):
    task_type = callback.data[len("listening_type_"):]
    if task_type == "one":
        task_type = "fill_one"
    elif task_type == "multiple":
        task_type = "fill_multiple"
    await state.update_data({"task_type": task_type})
    await state.set_state(ListeningState.choosing_level)
    text = "Выберите уровень:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(task_type))
    await callback.answer()

@router.callback_query(ListeningState.choosing_level, F.data.startswith("listening_level_"))
async def level_selected(callback: CallbackQuery, state: FSMContext):
    rest = callback.data[len("listening_level_"):]
    parts = rest.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("Ошибка.", show_alert=True)
        return
    task_type, level = parts[0], parts[1]
    if task_type == "one":
        task_type = "fill_one"
    elif task_type == "multiple":
        task_type = "fill_multiple"
    user_id = callback.from_user.id

    try:
        await callback.message.delete()
    except:
        pass

    tasks = get_tasks_by_type_and_level(task_type, level)
    if not tasks:
        await callback.answer("Нет заданий.", show_alert=True)
        return

    correct, wrong = await get_user_stats_db(user_id, make_listening_type_key(task_type), level)

    order_key = get_order_key(task_type, level)
    content_str = json.dumps(tasks, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
    saved_hash = await get_order_hash(user_id, order_key)

    if saved_hash is None or saved_hash != current_hash:
        order = list(range(len(tasks)))
        random.shuffle(order)
        shuffled_order = order
        await set_random_order(user_id, order_key, shuffled_order)
        await set_order_hash(user_id, order_key, current_hash)
        await reset_progress_index(user_id, make_listening_type_key(task_type), level)
        logger.info(f"Задания {order_key} изменились, создан новый порядок, хеш={current_hash[:8]}...")
    else:
        shuffled_order = await get_random_order(user_id, order_key)
        if shuffled_order is None:
            order = list(range(len(tasks)))
            random.shuffle(order)
            shuffled_order = order
            await set_random_order(user_id, order_key, shuffled_order)
            await set_order_hash(user_id, order_key, current_hash)

    shuffled_order = ensure_list_of_ints(shuffled_order)
    if not shuffled_order:
        order = list(range(len(tasks)))
        random.shuffle(order)
        shuffled_order = order
        await set_random_order(user_id, order_key, shuffled_order)

    await state.update_data({
        "task_type": task_type,
        "level": level,
        "correct": correct,
        "wrong": wrong,
        "session_correct": 0,
        "session_wrong": 0,
        "total": len(tasks),
        "index": 0,
        "question_message_id": None,
        "progress_message_id": None,
        "is_revision": False,
        "user_id": user_id,
    })

    await update_progress_message(callback.message, state, user_id=user_id)
    await send_task(callback.message, state, user_id=user_id)
    await callback.answer()

# ========== ИСПРАВЛЕННАЯ ФУНКЦИЯ start_revision ==========
@router.callback_query(ListeningState.answering_task, F.data == "listening_revision")
async def start_revision(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if not task_type or not level:
        await callback.answer("Ошибка.", show_alert=True)
        return

    error_ids = await get_reading_errors_db(user_id, make_listening_type_key(task_type), level)

    if not error_ids:
        # Убираем кнопки у сообщения прогресса, если оно есть
        progress_msg_id = data.get("progress_message_id")
        if progress_msg_id:
            try:
                await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=progress_msg_id, reply_markup=None)
            except:
                pass
        await callback.message.answer("🎉 Ошибок нет. Отличная работа!")
        await callback.answer()
        return

    progress_msg_id = data.get("progress_message_id")
    question_msg_id = data.get("question_message_id")
    if question_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=question_msg_id, reply_markup=None)
        except:
            pass
        await state.update_data({"question_message_id": None})

    level_label = LEVELS.get(level, level)
    info_text = (
        f"Работа над ошибками\n"
        f"Тип: {TASK_TYPES[task_type]}\n"
        f"Уровень: {level_label}\n\n"
        f"Заданий на исправление: {len(error_ids)}"
    )

    # Редактируем существующее сообщение прогресса
    if progress_msg_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg_id,
                text=info_text,
                reply_markup=get_revision_info_keyboard(),
                parse_mode="HTML"
            )
            await state.update_data({"progress_message_id": progress_msg_id})
        except Exception as e:
            logger.error(f"Ошибка редактирования прогресса при ревизии: {e}")
            info_msg = await callback.message.answer(info_text, reply_markup=get_revision_info_keyboard())
            add_user_message(user_id, info_msg.message_id)
            await state.update_data({"progress_message_id": info_msg.message_id})
    else:
        info_msg = await callback.message.answer(info_text, reply_markup=get_revision_info_keyboard())
        add_user_message(user_id, info_msg.message_id)
        await state.update_data({"progress_message_id": info_msg.message_id})

    await state.set_state(ListeningState.revision_mode)
    await state.update_data({
        "revision_error_ids": error_ids,
        "revision_index": 0,
        "revision_fixed": 0,
        "revision_total": len(error_ids),
        "revision_info_msg_id": progress_msg_id
    })

    await send_task(callback.message, state, is_revision=True, task_type=task_type, level=level, error_ids=error_ids, user_id=user_id)
    await callback.answer()

# ========== ОБРАБОТЧИК ОТВЕТОВ (КНОПКИ) ==========
@router.callback_query(F.data.startswith("listening_answer_"))
async def handle_answer(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state not in (ListeningState.answering_task.state, ListeningState.revision_mode.state):
        await callback.answer("Вы не в режиме ответа.", show_alert=True)
        return

    data = await state.get_data()
    if data.get("answered", False):
        await callback.answer("Вы уже ответили на это задание.", show_alert=True)
        return

    task = data.get("task")
    if not task:
        await callback.answer("Ошибка: задание не найдено.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка формата.", show_alert=True)
        return

    answer_part = parts[3]
    is_revision = data.get("is_revision", False)

    is_correct = False
    result_text = ""

    if task["type"] in ["choice", "speaker"]:
        try:
            selected_index = int(answer_part)
        except ValueError:
            await callback.answer("Ошибка: неверный индекс.", show_alert=True)
            return
        correct_index = int(task["correct"])
        is_correct = (selected_index == correct_index)
        if is_correct:
            result_text = "Правильно! Ответ: " + task["options"][correct_index]
        else:
            result_text = f"Неправильно. Правильный ответ: {task['options'][correct_index]}"
    elif task["type"] == "truefalse":
        user_answer = answer_part
        correct = task["correct"]
        is_correct = (user_answer == correct)
        correct_label = {"true": "True", "false": "False", "notstated": "Not stated"}.get(correct, correct)
        if is_correct:
            result_text = f"Правильно! Ответ: {correct_label}"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct_label}"
    else:
        await callback.answer("Этот тип не поддерживается.", show_alert=True)
        return

    user_id = callback.from_user.id
    type_key = data["task_type"]
    level_key = data["level"]
    prefixed_key = make_listening_type_key(type_key)

    if is_revision:
        if is_correct:
            await remove_reading_error_db(user_id, prefixed_key, level_key, task["id"])
            await state.update_data({"revision_fixed": data.get("revision_fixed", 0) + 1})
    else:
        if is_correct:
            await update_user_stats_db(user_id, prefixed_key, level_key, True)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data({"session_correct": session_correct})
        else:
            await update_user_stats_db(user_id, prefixed_key, level_key, False)
            await add_reading_error_db(user_id, prefixed_key, level_key, task["id"])
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data({"session_wrong": session_wrong})

    question_msg_id = data.get("question_message_id")
    if question_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=question_msg_id,
                reply_markup=None
            )
        except:
            pass
        await state.update_data({"question_message_id": None})

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logger.warning(f"Ошибка при убирании кнопок: {e}")

    await update_progress_message(callback.message, state, user_id=user_id)

    msg = await callback.message.answer(result_text)
    add_user_message(user_id, msg.message_id)

    await state.update_data({"answered": True})
    await callback.answer()

    if is_revision:
        await go_to_next_revision(callback.message, state, user_id=user_id)
    else:
        await go_to_next_task(callback.message, state, user_id=user_id)

# ========== "ПОКАЗАТЬ ОТВЕТ" (ОБЫЧНЫЙ РЕЖИМ) ==========
@router.callback_query(ListeningState.answering_task, F.data.startswith("listening_show_answer_"))
async def show_answer_normal(callback: CallbackQuery, state: FSMContext):
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

        question_msg_id = data.get("question_message_id")
        if question_msg_id:
            try:
                await callback.bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=question_msg_id,
                    reply_markup=None
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    logger.warning(f"Ошибка: {e}")

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.warning(f"Ошибка: {e}")

        msg = await callback.message.answer(f"Правильный ответ: {answer_text}")
        add_user_message(callback.from_user.id, msg.message_id)

        await state.update_data({"answered": True})
        await callback.answer()
        await go_to_next_task(callback.message, state, user_id=callback.from_user.id)

    except Exception as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"Ошибка в show_answer_normal: {e}")
            await callback.answer("Произошла ошибка.", show_alert=True)

# ========== "ПОКАЗАТЬ ОТВЕТ" (РЕВИЗИЯ) ==========
@router.callback_query(ListeningState.revision_mode, F.data.startswith("listening_show_answer_"))
async def show_answer_revision(callback: CallbackQuery, state: FSMContext):
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

        question_msg_id = data.get("question_message_id")
        if question_msg_id:
            try:
                await callback.bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=question_msg_id,
                    reply_markup=None
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    logger.warning(f"Ошибка: {e}")

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.warning(f"Ошибка: {e}")

        msg = await callback.message.answer(f"Правильный ответ: {answer_text}")
        add_user_message(callback.from_user.id, msg.message_id)

        await state.update_data({"answered": True})
        await callback.answer()
        await go_to_next_revision(callback.message, state, user_id=callback.from_user.id)

    except Exception as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"Ошибка в show_answer_revision: {e}")
            await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(ListeningState.revision_mode, F.data == "revision_finish_card")
async def finish_revision_card(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await finish_revision_with_summary(callback.message, state, user_id=callback.from_user.id)

# ========== MIDDLEWARE ДЛЯ ТЕКСТОВЫХ ОТВЕТОВ ==========
@router.message.outer_middleware()
async def listening_text_middleware(call: types.Message, event: types.Message, data: dict):
    state: FSMContext = data.get('state')
    if not state:
        return await call(event, data)
    current_state = await state.get_state()
    if not current_state or not current_state.startswith("ListeningState"):
        return await call(event, data)
    text = event.text or ""
    if text and text.startswith('/'):
        return await call(event, data)
    if current_state == ListeningState.answering_task.state or current_state == ListeningState.revision_mode.state:
        if text:
            await handle_text_answer(event, state)
            return
        else:
            return await call(event, data)
    await event.answer("Используйте кнопки.")
    return

async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id") or message.from_user.id

    if data.get("answered", False):
        await message.answer("Уже отвечено.")
        if data.get("is_revision", False):
            await go_to_next_revision(message, state, user_id=user_id)
        else:
            await go_to_next_task(message, state, user_id=user_id)
        return

    task = data.get("task")
    if not task:
        await message.answer("Ошибка.")
        return

    user_input = message.text.strip()
    if not user_input:
        await message.answer("Введите ответ.")
        return

    task_type = task["type"]
    if task_type in ["choice", "truefalse", "speaker"]:
        await message.answer("Ответьте, нажав на кнопку.")
        return

    is_correct = False
    result_text = ""

    if task_type == "fill_one":
        correct = task["correct"]
        if normalize_text_answer(user_input) == normalize_text_answer(correct):
            is_correct = True
            result_text = f"Правильно! Ответ: {correct}"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct}"
    elif task_type == "fill_multiple":
        user_answers = [normalize_text_answer(a) for a in user_input.split(';') if a.strip()]
        correct_answers = [normalize_text_answer(a) for a in task["answers"]]
        if len(user_answers) != len(correct_answers):
            is_correct = False
            result_text = f"Неправильно. Правильные ответы: {'; '.join(task['answers'])}"
        else:
            all_correct = all(u == c for u, c in zip(user_answers, correct_answers))
            if all_correct:
                is_correct = True
                result_text = f"Правильно! Ответ: {'; '.join(task['answers'])}"
            else:
                result_text = f"Неправильно. Правильные ответы: {'; '.join(task['answers'])}"
    else:
        await message.answer("Ответьте, нажав на кнопку.")
        return

    type_key = data["task_type"]
    level_key = data["level"]
    prefixed_key = make_listening_type_key(type_key)

    if data.get("is_revision", False):
        if is_correct:
            await remove_reading_error_db(user_id, prefixed_key, level_key, task["id"])
            await state.update_data({"revision_fixed": data.get("revision_fixed", 0) + 1})
    else:
        if is_correct:
            await update_user_stats_db(user_id, prefixed_key, level_key, True)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data({"session_correct": session_correct})
        else:
            await update_user_stats_db(user_id, prefixed_key, level_key, False)
            await add_reading_error_db(user_id, prefixed_key, level_key, task["id"])
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data({"session_wrong": session_wrong})

    question_msg_id = data.get("question_message_id")
    if question_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=question_msg_id,
                reply_markup=None
            )
        except:
            pass
        await state.update_data({"question_message_id": None})

    await update_progress_message(message, state, user_id=user_id)

    msg = await message.answer(result_text)
    add_user_message(user_id, msg.message_id)

    await state.update_data({"answered": True})

    if data.get("is_revision", False):
        await go_to_next_revision(message, state, user_id=user_id)
    else:
        await go_to_next_task(message, state, user_id=user_id)

@router.message(~F.text, StateFilter(ListeningState.answering_task, ListeningState.revision_mode))
async def handle_non_text_input(message: Message, state: FSMContext):
    data = await state.get_data()
    task = data.get("task")
    if not task:
        await message.answer("Используйте кнопки.")
        return
    task_type = task["type"]
    if task_type in ["choice", "truefalse", "speaker"]:
        await message.answer("Ответьте, нажав на кнопку.")
    elif task_type in ["fill_one", "fill_multiple"]:
        await message.answer("Введите текстовый ответ.")
    else:
        await message.answer("Используйте кнопки.")

# ========== ЗАВЕРШЕНИЕ СЕССИИ И СБРОСЫ ==========
@router.callback_query(ListeningState.answering_task, F.data == "listening_finish")
@router.callback_query(ListeningState.revision_mode, F.data == "listening_finish")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    current_state = await state.get_state()

    if current_state == ListeningState.revision_mode.state:
        await finish_revision_with_summary(callback.message, state, user_id=user_id)
        await callback.answer()
        return

    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)
    total = session_correct + session_wrong

    await clear_user_buttons(user_id, callback.bot, chat_id)

    if total == 0:
        stats = "Вы не сделали ни одного задания."
    else:
        stats = f"✔️ Правильно: {session_correct}\n✖️ Ошибок: {session_wrong}"

    msg = await callback.message.answer(f"Сессия завершена 🙌🏽\n{stats}")
    add_user_message(user_id, msg.message_id)

    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=False)
    await callback.answer()

@router.callback_query(F.data == "listening_finish_session")
async def finish_session_direct(callback: CallbackQuery, state: FSMContext):
    await finish_session(callback, state)

# ---------- СБРОС ПРОГРЕССА ----------
@router.callback_query(ListeningState.answering_task, F.data == "listening_reset_progress")
async def reset_progress_request(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    progress_msg_id = data.get("progress_message_id")
    if not progress_msg_id:
        await callback.answer("Ошибка.", show_alert=True)
        return

    text = "Вы уверенны? Все ошибки и правильные ответы будут обнулены.\nЗадания будут даны с самого начала."
    try:
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=progress_msg_id,
            text=text,
            reply_markup=get_confirm_reset_progress_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка reset: {e}")
        await callback.answer("Ошибка.", show_alert=True)
        return

    await state.set_state(ListeningState.confirm_reset)
    await callback.answer()

@router.callback_query(ListeningState.confirm_reset, F.data == "confirm_reset_progress_yes")
async def confirm_reset_progress(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if not task_type or not level:
        await callback.answer("Ошибка.", show_alert=True)
        return

    question_msg_id = data.get("question_message_id")
    if question_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=question_msg_id, reply_markup=None)
        except:
            pass
        await state.update_data({"question_message_id": None})

    progress_msg_id = data.get("progress_message_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=progress_msg_id, reply_markup=None)
        except:
            pass

    await reset_progress_index(user_id, make_listening_type_key(task_type), level)
    await reset_user_stats_db(user_id, make_listening_type_key(task_type), level)
    await clear_reading_errors_db(user_id, make_listening_type_key(task_type), level)

    order_key = get_order_key(task_type, level)
    tasks = get_tasks_by_type_and_level(task_type, level)
    new_order = list(range(len(tasks)))
    random.shuffle(new_order)
    await set_random_order(user_id, order_key, new_order)
    content_str = json.dumps(tasks, sort_keys=True, ensure_ascii=False)
    new_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
    await set_order_hash(user_id, order_key, new_hash)

    if progress_msg_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg_id,
                text="Прогресс сброшен.\nЗадания даны с самого начала.",
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Ошибка после сброса: {e}")

    await state.update_data({"session_correct": 0, "session_wrong": 0, "index": 0, "question_message_id": None})
    await state.set_state(ListeningState.answering_task)

    await update_progress_message(callback.message, state, reset=True, user_id=user_id)
    await send_task(callback.message, state, user_id=user_id)
    await callback.answer()

@router.callback_query(ListeningState.confirm_reset, F.data == "confirm_reset_progress_no")
async def cancel_reset_progress(callback: CallbackQuery, state: FSMContext):
    await update_progress_message(callback.message, state)
    await state.set_state(ListeningState.answering_task)
    await callback.answer("Отмена.")

# ---------- СБРОС ОШИБОК ----------
@router.callback_query(ListeningState.revision_mode, F.data == "revision_reset_errors")
async def reset_errors_request(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    info_msg_id = data.get("revision_info_msg_id")
    if not info_msg_id:
        await callback.answer("Ошибка.", show_alert=True)
        return

    text = (
        "Вы уверены, что хотите сбросить все ошибки для этого типа заданий?\n"
        "Ошибки будут удалены, вы продолжите с места на котором остановились.\n\n"
        "Это действие нельзя отменить."
    )
    try:
        await callback.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=info_msg_id,
            text=text,
            reply_markup=get_confirm_reset_errors_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка reset errors: {e}")
        await callback.answer("Ошибка.", show_alert=True)
        return

    await state.set_state(ListeningState.confirm_reset_errors)
    await callback.answer()

@router.callback_query(ListeningState.confirm_reset_errors, F.data == "confirm_reset_errors_yes")
async def confirm_reset_errors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if not task_type or not level:
        await callback.answer("Ошибка.", show_alert=True)
        return

    await clear_reading_errors_db(user_id, make_listening_type_key(task_type), level)

    await update_progress_message(callback.message, state, user_id=user_id)

    info_msg_id = data.get("revision_info_msg_id")
    if info_msg_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=info_msg_id,
                text="Ошибки сброшены.",
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")

    await exit_revision(callback.message, state, show_progress=True, user_id=user_id)
    await callback.answer()

@router.callback_query(ListeningState.confirm_reset_errors, F.data == "confirm_reset_errors_no")
async def cancel_reset_errors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    user_id = callback.from_user.id

    error_ids = await get_reading_errors_db(user_id, make_listening_type_key(task_type), level)
    count = len(error_ids)
    level_label = LEVELS.get(level, level)
    text = f"Работа над ошибками\nТип: {TASK_TYPES[task_type]}\nУровень: {level_label}\n\nЗаданий: {count}"
    info_msg_id = data.get("revision_info_msg_id")
    if info_msg_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=info_msg_id,
                text=text,
                reply_markup=get_revision_info_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")

    await state.set_state(ListeningState.revision_mode)
    await callback.answer("Отмена.")

@router.callback_query(ListeningState.revision_mode, F.data == "revision_back_to_study")
async def revision_back_to_study(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await exit_revision(callback.message, state, show_progress=True, user_id=callback.from_user.id)

@router.callback_query(ListeningState.choosing_level, F.data == "listening_back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    await state.set_state(ListeningState.choosing_type)
    await state.update_data({"user_id": user_id})
    text = "Аудирование 🎧\n\nВыберите режим:"
    try:
        await callback.message.edit_text(text, reply_markup=get_types_keyboard())
    except Exception as e:
        logger.warning(f"Ошибка: {e}")
        msg = await callback.message.answer(text, reply_markup=get_types_keyboard())
        add_user_message(user_id, msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "listening_back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    await clear_user_buttons(user_id, callback.bot, chat_id)
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

# ========== ФУНКЦИЯ ДЛЯ ВЫЗОВА ИЗ START.PY ==========
async def start_listening(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await listening_start(callback, state)