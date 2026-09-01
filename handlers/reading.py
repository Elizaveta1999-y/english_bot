import logging
import random
import json
import hashlib
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from data.reading_loader import get_task, TASKS
from utils.db import (
    get_user_stats_db as get_user_stats,
    update_user_stats_db as update_user_stats,
    reset_user_stats_db as reset_user_stats,
    add_reading_error_db as add_reading_error,
    remove_reading_error_db as remove_reading_error,
    get_reading_errors_db as get_reading_errors,
    clear_reading_errors_db as clear_reading_errors,
    get_progress_index,
    set_progress_index,
    reset_progress_index,
    get_random_order,
    set_random_order,
    get_order_hash,
    set_order_hash,
    get_connection,
)
from states.reading_states import ReadingStates
from data.users import get_user_state, set_user_state

logger = logging.getLogger(__name__)
router = Router()

# ---------- Константы ----------
TYPE_DISPLAY = {
    "podbor": "🥈 Подбор заголовка",
    "truefalse": "⚖️ True/False/Not stated",
    "choice": "☑️ Вопросы с выбором ответа",
    "order": "📄 Восстановление порядка абзацев",
}

TYPE_MAP = {
    "podbor": "Подбор_заголовка",
    "truefalse": "True_False_Not_stated",
    "choice": "Вопросы_с_выбором_ответа",
    "order": "Восстановление_порядка_абзацев"
}

LEVEL_MAP = {
    "beginner": "Новичок",
    "intermediate": "Любитель",
    "expert": "Эксперт"
}

def get_level_display(level_key: str) -> str:
    emojis = {
        "beginner": "🌱",
        "intermediate": "📚",
        "expert": "🎓"
    }
    return f"{emojis.get(level_key, '')} {LEVEL_MAP.get(level_key, level_key)}".strip()

TYPE_DESCRIPTION = {
    "podbor": "подберите заголовок к тексту",
    "truefalse": "определите, верно ли утверждение",
    "choice": "выберите правильный ответ на вопрос",
    "order": "восстановите порядок абзацев",
}

# ---------- Вспомогательная функция для приведения порядка ----------
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

def make_type_key(type_json: str, level_json: str) -> str:
    return f"reading_{type_json}_{level_json}"

def get_tasks_by_type_and_level(type_json, level_json):
    tasks = []
    if type_json in TASKS:
        tasks_data = TASKS[type_json]
        if isinstance(tasks_data, dict):
            tasks = tasks_data.get(level_json, [])
        elif isinstance(tasks_data, list):
            tasks = [t for t in tasks_data if t.get("level") == level_json]
    return tasks

# ---------- Клавиатуры ----------
def get_type_choice_keyboard():
    buttons = []
    for key, label in TYPE_DISPLAY.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"reading_type:{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_keyboard(short_type: str):
    buttons = [
        [InlineKeyboardButton(text=get_level_display("beginner"), callback_data=f"reading_level:{short_type}:beginner")],
        [InlineKeyboardButton(text=get_level_display("intermediate"), callback_data=f"reading_level:{short_type}:intermediate")],
        [InlineKeyboardButton(text=get_level_display("expert"), callback_data=f"reading_level:{short_type}:expert")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_types")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_action_keyboard(short_type: str, short_level: str, index: int, is_revision: bool = False):
    rev_flag = "rev" if is_revision else "norm"
    buttons = [
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"reading_show_answer:{short_type}:{short_level}:{index}:{rev_flag}"),
            InlineKeyboardButton(text="Завершить", callback_data="reading_finish_session")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_progress_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="reading_revision")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="reading_reset")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_reset_confirmation_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Да, сбросить", callback_data="reading_confirm_reset")],
        [InlineKeyboardButton(text="Назад", callback_data="reading_cancel_reset")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_clear_errors_confirmation_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Да, сбросить", callback_data="reading_confirm_clear_errors")],
        [InlineKeyboardButton(text="Назад", callback_data="reading_cancel_clear_errors")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Очистка клавиатур ----------
async def clear_task_keyboard(message: Message, state: FSMContext):
    data = await state.get_data()
    last_id = data.get("last_task_msg_id")
    if last_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=last_id, reply_markup=None)
        except Exception:
            pass
        await state.update_data(last_task_msg_id=None)

async def clear_all_keyboards(message: Message, state: FSMContext):
    data = await state.get_data()
    last_id = data.get("last_task_msg_id")
    if last_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=last_id, reply_markup=None)
        except Exception:
            pass
        await state.update_data(last_task_msg_id=None)
    progress_id = data.get("progress_msg_id")
    if progress_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=progress_id, reply_markup=None)
        except Exception:
            pass
        await state.update_data(progress_msg_id=None)

# ---------- Отправка задания ----------
async def render_task_message(message: Message, state: FSMContext, user_id: int, short_type: str, short_level: str, index: int = 0, task_id: int = None, paragraph_idx: int = 0, is_revision: bool = False):
    await clear_task_keyboard(message, state)

    data = await state.get_data()

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    tasks = get_tasks_by_type_and_level(type_json, level_json)

    if task_id is not None:
        task = get_task_by_id_for_type(type_json, level_json, task_id)
        if not task:
            return None, None
        await state.update_data(actual_type=short_type, actual_task=task, current_task_id=task_id)
    else:
        shuffled_order = data.get("shuffled_order")
        if shuffled_order is None:
            shuffled_order = await get_random_order(user_id, make_type_key(type_json, level_json))
            if shuffled_order is None:
                order = list(range(len(tasks)))
                random.shuffle(order)
                shuffled_order = order
                await set_random_order(user_id, make_type_key(type_json, level_json), shuffled_order)
            await state.update_data(shuffled_order=shuffled_order)

        if not shuffled_order:
            shuffled_order = list(range(len(tasks)))
            await set_random_order(user_id, make_type_key(type_json, level_json), shuffled_order)
            await state.update_data(shuffled_order=shuffled_order)

        if index >= len(shuffled_order):
            index = 0
            await set_progress_index(user_id, type_json, level_json, 0)
            await state.update_data(index=0)

        real_index = shuffled_order[index]
        if real_index >= len(tasks):
            real_index = 0
            await set_progress_index(user_id, type_json, level_json, 0)
            await state.update_data(index=0)
            real_index = shuffled_order[0]

        task = tasks[real_index]
        if not task:
            return None, None
        await state.update_data(actual_type=short_type, actual_task=task, current_task_id=task.get("id"))

    paragraphs = task.get("paragraphs", [])
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    if not paragraphs:
        paragraphs = ["(текст отсутствует)"]

    text = ""

    if short_type == "order":
        for i, para in enumerate(paragraphs):
            if not para.startswith(chr(65+i) + ")"):
                text += f"{chr(65+i)}) {para}\n\n"
            else:
                text += f"{para}\n\n"
        text += f"{task.get('question', '')}"
    else:
        if short_type == "truefalse":
            text += f"{paragraphs[0]}\n\n"
            text += f"{task.get('statement', '')}\n\nВыберите верное утверждение:"
        else:
            text += f"{paragraphs[0]}\n\n"
            text += f"{task.get('question', '')}\n"

    is_text_input = task.get("input_type") == "text"

    if short_type == "order":
        keyboard = get_action_keyboard(short_type, short_level, index, is_revision)
    elif is_text_input:
        text += "\nВведите ответ в чат."
        keyboard = get_action_keyboard(short_type, short_level, index, is_revision)
    else:
        options = task.get("options", [])
        kb_buttons = []
        for i, opt in enumerate(options):
            kb_buttons.append([InlineKeyboardButton(text=opt, callback_data=f"reading_answer:{short_type}:{short_level}:{index}:{i}:{'rev' if is_revision else 'norm'}")])
        kb_buttons.append([
            InlineKeyboardButton(text="Показать ответ", callback_data=f"reading_show_answer:{short_type}:{short_level}:{index}:{'rev' if is_revision else 'norm'}"),
            InlineKeyboardButton(text="Завершить", callback_data="reading_finish_session")
        ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(last_task_msg_id=sent_msg.message_id)

    if is_text_input:
        await state.set_state(ReadingStates.waiting_for_text)
    else:
        await state.set_state(ReadingStates.in_progress)

    return text, keyboard

def get_task_by_id_for_type(type_json: str, level_json: str, task_id: int):
    if type_json in TASKS:
        tasks = TASKS[type_json]
        if isinstance(tasks, dict):
            tasks = tasks.get(level_json, [])
        elif isinstance(tasks, list):
            tasks = [t for t in tasks if t.get("level") == level_json]
        for t in tasks:
            if t.get("id", -1) == task_id:
                return t
    return None

async def get_total_stats(user_id: int, short_level: str):
    total_correct = 0
    total_wrong = 0
    level_json = LEVEL_MAP.get(short_level, short_level)
    for type_key in TYPE_MAP.keys():
        type_json = TYPE_MAP[type_key]
        correct, wrong = await get_user_stats(user_id, type_json, level_json)
        total_correct += correct
        total_wrong += wrong
    return total_correct, total_wrong

# ---------- ИСПРАВЛЕННАЯ ФУНКЦИЯ ОБНОВЛЕНИЯ ПРОГРЕССА (с логированием) ----------
async def update_progress_message(message: Message, user_id: int, short_type: str, short_level: str, state: FSMContext):
    data = await state.get_data()
    progress_msg_id = data.get("progress_msg_id")

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    correct, _ = await get_user_stats(user_id, type_json, level_json)
    errors = await get_reading_errors(user_id, type_json, level_json)
    error_count = len(errors)
    display_name = TYPE_DISPLAY.get(short_type, short_type)
    level_display = get_level_display(short_level)
    description = TYPE_DESCRIPTION.get(short_type, "выполните задание")

    text = f"<b>Режим:</b> {display_name}\n"
    text += f"<b>Уровень:</b> {level_display}\n\n"
    text += f"Внимательно прочитайте текст и {description}.\n\n"
    text += f"Ваш прогресс:\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {error_count}"

    if progress_msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=progress_msg_id,
                text=text,
                reply_markup=get_progress_keyboard(),
                parse_mode="HTML"
            )
            logger.debug(f"Прогресс обновлён (редактирование) msg_id={progress_msg_id}")
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать прогресс msg_id={progress_msg_id}: {e}")
            # Если редактирование не удалось – отправляем новое
            sent_msg = await message.answer(text, reply_markup=get_progress_keyboard(), parse_mode="HTML")
            await state.update_data(progress_msg_id=sent_msg.message_id)
            logger.debug(f"Отправлено новое сообщение прогресса msg_id={sent_msg.message_id}")
            return

    # Если progress_msg_id отсутствует – отправляем новое
    sent_msg = await message.answer(text, reply_markup=get_progress_keyboard(), parse_mode="HTML")
    await state.update_data(progress_msg_id=sent_msg.message_id)
    logger.debug(f"Отправлено новое сообщение прогресса msg_id={sent_msg.message_id}")

# -------------------- Обработчики --------------------
@router.callback_query(F.data == "start_reading")
async def start_reading(callback: CallbackQuery, state: FSMContext):
    await clear_all_keyboards(callback.message, state)
    await callback.message.edit_text("📖 Чтение\n\nВыберите режим:", reply_markup=get_type_choice_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "reading_back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await clear_all_keyboards(callback.message, state)
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("reading_type:"))
async def choose_type(callback: CallbackQuery):
    short_type = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        "Выберите уровень сложности:",
        reply_markup=get_level_keyboard(short_type),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "reading_back_to_types")
async def back_to_types(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите тип задания:",
        reply_markup=get_type_choice_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("reading_level:"))
async def choose_level(callback: CallbackQuery, state: FSMContext):
    _, short_type, short_level = callback.data.split(":")
    user_id = callback.from_user.id

    user_state = get_user_state(user_id)
    user_state["mode"] = None
    set_user_state(user_id, user_state)

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    level_key = make_type_key(type_json, level_json)

    tasks = get_tasks_by_type_and_level(type_json, level_json)
    if not tasks:
        await callback.message.edit_text("Задания для этого уровня пока отсутствуют. Попробуйте другой уровень.")
        await callback.answer()
        return

    content_str = json.dumps(tasks, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
    logger.info(f"Текущий хеш для {level_key}: {current_hash[:8]}...")

    saved_hash = await get_order_hash(user_id, level_key)
    shuffled_order = await get_random_order(user_id, level_key)

    need_recreate = False
    reasons = []

    if saved_hash is None:
        reasons.append("Хеш отсутствует")
        need_recreate = True
    elif saved_hash != current_hash:
        reasons.append("Хеш изменился")
        need_recreate = True
    elif shuffled_order is None:
        reasons.append("Порядок отсутствует")
        need_recreate = True
    elif len(shuffled_order) != len(tasks):
        reasons.append(f"Длина не совпадает (БД={len(shuffled_order)}, файл={len(tasks)})")
        need_recreate = True
    elif any(idx >= len(tasks) for idx in shuffled_order):
        reasons.append("Есть невалидные индексы")
        need_recreate = True
    elif shuffled_order == list(range(len(tasks))):
        reasons.append("Порядок не перемешан")
        need_recreate = True

    if reasons:
        logger.info(f"Причины пересоздания для {level_key}: {', '.join(reasons)}")
    else:
        logger.info(f"Все проверки пройдены для {level_key}, порядок валидный")

    if need_recreate:
        logger.info(f"!!! ПЕРЕСОЗДАЁМ ПОРЯДОК для {level_key} !!!")
        conn = await get_connection()
        await conn.execute("DELETE FROM random_order WHERE user_id = $1 AND level_key = $2", user_id, level_key)
        await conn.close()
        logger.info("Старая запись удалена")

        new_order = list(range(len(tasks)))
        random.shuffle(new_order)
        shuffled_order = new_order
        logger.info(f"Новый порядок: {shuffled_order[:30]}...")

        await set_random_order(user_id, level_key, shuffled_order)
        await set_order_hash(user_id, level_key, current_hash)
        await reset_progress_index(user_id, type_json, level_json)
        index = 0
        logger.info("Новый порядок сохранён, хеш обновлён, индекс сброшен на 0")
    else:
        shuffled_order = ensure_list_of_ints(shuffled_order)
        if not shuffled_order:
            logger.warning(f"Некорректный порядок для {level_key}, пересоздаём")
            new_order = list(range(len(tasks)))
            random.shuffle(new_order)
            shuffled_order = new_order
            await set_random_order(user_id, level_key, shuffled_order)
            await set_order_hash(user_id, level_key, current_hash)
            await reset_progress_index(user_id, type_json, level_json)
            index = 0
        else:
            index = await get_progress_index(user_id, type_json, level_json)
            if index >= len(shuffled_order):
                index = 0
                await set_progress_index(user_id, type_json, level_json, 0)

    await state.update_data(shuffled_order=shuffled_order, index=index)

    await state.update_data(
        short_type=short_type,
        short_level=short_level,
        paragraph_idx=0,
        is_revision=False,
        error_list=[],
        error_index=0,
        last_task_msg_id=None,
        revision_correct=0,
        revision_wrong=0,
        session_correct=0,
        session_wrong=0,
        progress_msg_id=None,
        total_errors_start=0,
        current_task_id=None
    )

    await state.set_state(ReadingStates.in_progress)

    await update_progress_message(callback.message, user_id, short_type, short_level, state)
    await render_task_message(callback.message, state, user_id, short_type, short_level, index, paragraph_idx=0, is_revision=False)
    await callback.answer()

# ---------- Обработка ответов (кнопки) ----------
@router.callback_query(ReadingStates.in_progress, F.data.startswith("reading_answer:"))
@router.callback_query(ReadingStates.waiting_for_text, F.data.startswith("reading_answer:"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 6:
        await callback.answer("Ошибка формата")
        return
    short_type, short_level, index_str, chosen_idx_str, mode = parts[1], parts[2], parts[3], parts[4], parts[5]
    index = int(index_str)
    chosen_idx = int(chosen_idx_str)
    is_revision = (mode == "rev")
    user_id = callback.from_user.id

    data = await state.get_data()
    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    tasks = get_tasks_by_type_and_level(type_json, level_json)

    task_id = data.get("current_task_id")
    if task_id is not None:
        task = get_task_by_id_for_type(type_json, level_json, task_id)
    else:
        shuffled_order = data.get("shuffled_order")
        if shuffled_order and index < len(shuffled_order):
            real_index = shuffled_order[index]
            task = tasks[real_index] if real_index < len(tasks) else None
        else:
            task = None
    if not task:
        await callback.answer("Задание не найдено")
        return

    correct = (chosen_idx == task["correct"])
    task_identifier = task["id"]

    if is_revision:
        if correct:
            await remove_reading_error(user_id, type_json, level_json, task_identifier)
            await update_user_stats(user_id, type_json, level_json, True)
            new_correct = data.get("revision_correct", 0) + 1
            await state.update_data(revision_correct=new_correct)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data(session_correct=session_correct)
        else:
            new_wrong = data.get("revision_wrong", 0) + 1
            await state.update_data(revision_wrong=new_wrong)
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data(session_wrong=session_wrong)
    else:
        if correct:
            await update_user_stats(user_id, type_json, level_json, True)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data(session_correct=session_correct)
            await remove_reading_error(user_id, type_json, level_json, task_identifier)
        else:
            await update_user_stats(user_id, type_json, level_json, False)
            await add_reading_error(user_id, type_json, level_json, task_identifier)
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data(session_wrong=session_wrong)

    await callback.message.edit_reply_markup(reply_markup=None)

    if correct:
        result_text = "Правильно!"
    else:
        correct_text = task['options'][task['correct']]
        if short_type == "order":
            explanation = task.get("explanation", "")
            if explanation:
                result_text = f"Неправильно. Правильный ответ: {correct_text}\n\n{explanation}"
            else:
                result_text = f"Неправильно. Правильный ответ: {correct_text}"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct_text}"
    await callback.message.answer(result_text)

    # Обновляем прогресс – теперь это будет редактировать существующее сообщение
    await update_progress_message(callback.message, user_id, short_type, short_level, state)

    if not is_revision:
        shuffled_order = data.get("shuffled_order")
        if not shuffled_order:
            shuffled_order = await get_random_order(user_id, make_type_key(type_json, level_json))
            if shuffled_order is None:
                order = list(range(len(tasks)))
                random.shuffle(order)
                shuffled_order = order
                await set_random_order(user_id, make_type_key(type_json, level_json), shuffled_order)
            await state.update_data(shuffled_order=shuffled_order)

        next_index = index + 1
        if next_index >= len(shuffled_order):
            next_index = 0
        await set_progress_index(user_id, type_json, level_json, next_index)
        await state.update_data(index=next_index)

    if is_revision:
        error_ids = await get_reading_errors(user_id, type_json, level_json)
        if not error_ids:
            rev_correct = data.get("revision_correct", 0)
            rev_wrong = data.get("revision_wrong", 0)
            if rev_correct > 0 and rev_wrong == 0:
                msg = "🎉 Вы исправили все ошибки! Возвращаемся в учебный режим."
            elif rev_correct > 0 and rev_wrong > 0:
                msg = f"Исправлено: {rev_correct}, Неправильно: {rev_wrong}.\nПродолжайте тренировку!"
            else:
                msg = "Все задания с ошибками просмотрены. Возвращаемся к учебному режиму."
            await callback.message.answer(msg)
            await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0)
            await update_progress_message(callback.message, user_id, short_type, short_level, state)
            await render_task_message(callback.message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)
            await callback.answer()
            return
        else:
            await show_revision_task(callback.message, state, error_ids)
            await callback.answer()
            return
    else:
        await render_task_message(callback.message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)
        await callback.answer()

# ---------- Обработка текстовых ответов ----------
@router.message(ReadingStates.waiting_for_text, F.text, ~F.text.startswith('/'))
async def handle_text_answer(message: Message, state: FSMContext):
    if message.text in ("📊 Я всё! Фидбек", "🏠 Главное меню"):
        return

    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    index = data.get("index")
    is_revision = data.get("is_revision", False)
    user_id = message.from_user.id

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    tasks = get_tasks_by_type_and_level(type_json, level_json)

    task_id = data.get("current_task_id")
    if task_id is not None:
        task = get_task_by_id_for_type(type_json, level_json, task_id)
    else:
        shuffled_order = data.get("shuffled_order")
        if shuffled_order and index < len(shuffled_order):
            real_index = shuffled_order[index]
            task = tasks[real_index] if real_index < len(tasks) else None
        else:
            task = None
    if not task:
        await message.answer("Задание не найдено.")
        return

    correct_answer = task.get("correct")
    user_input = message.text.strip()

    if isinstance(correct_answer, list):
        user_parts = [normalize_answer(p) for p in user_input.split(";") if p.strip()]
        correct_parts = [normalize_answer(p) for p in correct_answer]
        if len(user_parts) != len(correct_parts):
            correct = False
        else:
            correct = (user_parts == correct_parts)
    else:
        user_clean = normalize_answer(user_input)
        correct_clean = normalize_answer(str(correct_answer))
        correct = (user_clean == correct_clean)

    task_identifier = task["id"]

    if is_revision:
        if correct:
            await remove_reading_error(user_id, type_json, level_json, task_identifier)
            await update_user_stats(user_id, type_json, level_json, True)
            new_correct = data.get("revision_correct", 0) + 1
            await state.update_data(revision_correct=new_correct)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data(session_correct=session_correct)
        else:
            new_wrong = data.get("revision_wrong", 0) + 1
            await state.update_data(revision_wrong=new_wrong)
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data(session_wrong=session_wrong)
    else:
        if correct:
            await update_user_stats(user_id, type_json, level_json, True)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data(session_correct=session_correct)
            await remove_reading_error(user_id, type_json, level_json, task_identifier)
        else:
            await update_user_stats(user_id, type_json, level_json, False)
            await add_reading_error(user_id, type_json, level_json, task_identifier)
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data(session_wrong=session_wrong)

    await clear_task_keyboard(message, state)

    if correct:
        result_text = "Правильно!"
    else:
        if isinstance(correct_answer, list):
            correct_text = '; '.join(correct_answer)
        else:
            correct_text = str(correct_answer)
        if short_type == "order":
            explanation = task.get("explanation", "")
            if explanation:
                result_text = f"Неправильно. Правильный ответ: {correct_text}\n\n{explanation}"
            else:
                result_text = f"Неправильно. Правильный ответ: {correct_text}"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct_text}"
    await message.answer(result_text)

    await state.set_state(ReadingStates.in_progress)

    await update_progress_message(message, user_id, short_type, short_level, state)

    if not is_revision:
        shuffled_order = data.get("shuffled_order")
        if not shuffled_order:
            shuffled_order = await get_random_order(user_id, make_type_key(type_json, level_json))
            if shuffled_order is None:
                order = list(range(len(tasks)))
                random.shuffle(order)
                shuffled_order = order
                await set_random_order(user_id, make_type_key(type_json, level_json), shuffled_order)
            await state.update_data(shuffled_order=shuffled_order)

        next_index = index + 1
        if next_index >= len(shuffled_order):
            next_index = 0
        await set_progress_index(user_id, type_json, level_json, next_index)
        await state.update_data(index=next_index)

    if is_revision:
        error_ids = await get_reading_errors(user_id, type_json, level_json)
        if not error_ids:
            rev_correct = data.get("revision_correct", 0)
            rev_wrong = data.get("revision_wrong", 0)
            if rev_correct > 0 and rev_wrong == 0:
                msg = "🎉 Вы исправили все ошибки! Возвращаемся в учебный режим."
            elif rev_correct > 0 and rev_wrong > 0:
                msg = f"Исправлено: {rev_correct}, Неправильно: {rev_wrong}.\nПродолжайте тренировку!"
            else:
                msg = "Все задания с ошибками просмотрены. Возвращаемся к учебному режиму."
            await message.answer(msg)
            await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0)
            await update_progress_message(message, user_id, short_type, short_level, state)
            await render_task_message(message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)
            return
        else:
            await show_revision_task(message, state, error_ids)
            return
    else:
        await render_task_message(message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)

# ---------- Обработка текстовых сообщений в состоянии in_progress ----------
@router.message(ReadingStates.in_progress, F.text, ~F.text.startswith('/'))
async def handle_text_in_progress(message: Message, state: FSMContext):
    if message.text in ("📊 Я всё! Фидбек", "🏠 Главное меню"):
        return
    await message.answer("Ответьте, нажав на кнопку.")

# ---------- Игнорирование голосовых, фото, документов в текстовых заданиях ----------
@router.message(ReadingStates.waiting_for_text, F.voice | F.photo | F.document | F.video | F.audio | F.sticker)
async def handle_non_text_in_waiting_text(message: Message, state: FSMContext):
    await message.answer("Введите текстовый ответ.")

# ---------- Вспомогательные функции ----------
async def show_revision_task(message: Message, state: FSMContext, error_ids: list):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = message.from_user.id

    if not error_ids:
        await message.answer("🎉 Ошибок нет. Отличная работа!")
        return

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    task_id = error_ids[0]
    task = get_task_by_id_for_type(type_json, level_json, task_id)
    if not task:
        await message.answer("Задание для исправления не найдено.")
        return
    await state.update_data(actual_type=short_type, actual_task=task, current_task_id=task_id)
    await render_task_message(message, state, user_id, short_type, short_level, task_id=task_id, paragraph_idx=0, is_revision=True)
    await state.update_data(paragraph_idx=0, is_revision=True, error_list=error_ids, error_index=0)

@router.callback_query(ReadingStates.in_progress, F.data.startswith("reading_show_answer:"))
@router.callback_query(ReadingStates.waiting_for_text, F.data.startswith("reading_show_answer:"))
async def show_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("Ошибка формата")
        return
    short_type, short_level, index_str, mode = parts[1], parts[2], parts[3], parts[4]
    index = int(index_str)
    data = await state.get_data()
    is_revision = (mode == "rev")
    user_id = callback.from_user.id

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    tasks = get_tasks_by_type_and_level(type_json, level_json)

    task_id = data.get("current_task_id")
    if task_id is not None:
        task = get_task_by_id_for_type(type_json, level_json, task_id)
    else:
        shuffled_order = data.get("shuffled_order")
        if shuffled_order and index < len(shuffled_order):
            real_index = shuffled_order[index]
            task = tasks[real_index] if real_index < len(tasks) else None
        else:
            task = None
    if not task:
        await callback.answer("Задание не найдено")
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    correct = task.get("correct")

    if short_type == "order":
        if isinstance(correct, int):
            if "options" in task and correct < len(task["options"]):
                correct_text = task["options"][correct]
            else:
                correct_text = str(correct + 1)
        elif isinstance(correct, list):
            correct_text = ' -> '.join(str(c+1) for c in correct)
        else:
            correct_text = str(correct)
        explanation = task.get("explanation", "")
        if explanation:
            await callback.message.answer(f"Правильный ответ: {correct_text}\n\n{explanation}")
        else:
            await callback.message.answer(f"Правильный ответ: {correct_text}")
    else:
        if "options" in task and correct < len(task["options"]):
            correct_text = task["options"][correct]
        else:
            correct_text = str(correct)
        await callback.message.answer(f"Правильный ответ: {correct_text}")

    if is_revision:
        error_ids = await get_reading_errors(user_id, type_json, level_json)
        if not error_ids:
            rev_correct = data.get("revision_correct", 0)
            rev_wrong = data.get("revision_wrong", 0)
            if rev_correct > 0 and rev_wrong == 0:
                msg = "🎉 Вы исправили все ошибки! Возвращаемся в учебный режим."
            elif rev_correct > 0 and rev_wrong > 0:
                msg = f"Исправлено: {rev_correct}, Неправильно: {rev_wrong}.\nПродолжайте тренировку!"
            else:
                msg = "Все задания с ошибками просмотрены. Возвращаемся к учебному режим."
            await callback.message.answer(msg)
            await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0)
            await update_progress_message(callback.message, user_id, short_type, short_level, state)
            await render_task_message(callback.message, state, user_id, short_type, short_level, index, paragraph_idx=0, is_revision=False)
            await callback.answer()
            return
        else:
            await show_revision_task(callback.message, state, error_ids)
            await callback.answer()
            return
    else:
        shuffled_order = data.get("shuffled_order")
        if not shuffled_order:
            shuffled_order = await get_random_order(user_id, make_type_key(type_json, level_json))
            if shuffled_order is None:
                order = list(range(len(tasks)))
                random.shuffle(order)
                shuffled_order = order
                await set_random_order(user_id, make_type_key(type_json, level_json), shuffled_order)
            await state.update_data(shuffled_order=shuffled_order)

        next_index = index + 1
        if next_index >= len(shuffled_order):
            next_index = 0
        await set_progress_index(user_id, type_json, level_json, next_index)
        await state.update_data(index=next_index)
        await render_task_message(callback.message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)
        await callback.answer()

@router.callback_query(ReadingStates.in_progress, F.data == "reading_revision")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_revision")
@router.message(Command("revision_mode"))
async def reading_revision(event, state: FSMContext):
    if isinstance(event, CallbackQuery):
        user_id = event.from_user.id
        message = event.message
        answer_func = event.answer
        current_state = await state.get_state()
        if current_state not in (ReadingStates.in_progress.state, ReadingStates.waiting_for_text.state):
            if answer_func:
                await answer_func("Сначала выберите тип и уровень в режиме чтения.", show_alert=True)
            return
    else:
        user_id = event.from_user.id
        message = event
        answer_func = None
        current_state = await state.get_state()
        if current_state not in (ReadingStates.in_progress.state, ReadingStates.waiting_for_text.state):
            await message.answer("Сначала выберите тип и уровень в режиме чтения.")
            return

    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")

    if not short_type or not short_level:
        text = "Сначала выберите тип и уровень в режиме чтения."
        if answer_func:
            await answer_func(text, show_alert=True)
        else:
            await message.answer(text)
        return

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)

    error_ids = await get_reading_errors(user_id, type_json, level_json)

    if not error_ids:
        await message.answer("🎉 Ошибок нет! Отличная работа.")
        if answer_func:
            await answer_func()
        return

    await state.update_data(
        is_revision=True,
        error_list=error_ids,
        error_index=0,
        revision_correct=0,
        revision_wrong=0,
        session_correct=0,
        session_wrong=0,
        total_errors_start=len(error_ids)
    )

    display_name = TYPE_DISPLAY.get(short_type, short_type)
    level_display = get_level_display(short_level)
    text = f"<b>Работа над ошибками</b>\nТип: {display_name}\nУровень: {level_display}\n\nЗаданий на исправление: {len(error_ids)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Учебный режим", callback_data="reading_back_to_mode")],
        [InlineKeyboardButton(text="Сбросить ошибки", callback_data="reading_clear_errors")]
    ])
    await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    await show_revision_task(message, state, error_ids)
    if answer_func:
        await answer_func()

# ---------- Подтверждение сброса ошибок ----------
@router.callback_query(ReadingStates.in_progress, F.data == "reading_clear_errors")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_clear_errors")
async def clear_errors_confirm(callback: CallbackQuery, state: FSMContext):
    confirm_text = "Вы уверены, что хотите сбросить все ошибки для этого типа заданий?\nОшибки будут удалены, вы продолжите с места на котором остановились.\n\nЭто действие нельзя отменить."
    await callback.message.edit_text(
        confirm_text,
        reply_markup=get_clear_errors_confirmation_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(ReadingStates.in_progress, F.data == "reading_confirm_clear_errors")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_confirm_clear_errors")
async def confirm_clear_errors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = callback.from_user.id

    if not short_type or not short_level:
        await callback.answer("Не удалось определить режим.", show_alert=True)
        return

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)

    await clear_reading_errors(user_id, type_json, level_json)

    await callback.message.edit_text("Ошибки сброшены.")
    await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0, session_correct=0, session_wrong=0)
    await update_progress_message(callback.message, user_id, short_type, short_level, state)
    await render_task_message(callback.message, state, user_id, short_type, short_level, data.get("index", 0), paragraph_idx=0, is_revision=False)
    await callback.answer()

@router.callback_query(ReadingStates.in_progress, F.data == "reading_cancel_clear_errors")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_cancel_clear_errors")
async def cancel_clear_errors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = callback.from_user.id

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    error_ids = await get_reading_errors(user_id, type_json, level_json)

    display_name = TYPE_DISPLAY.get(short_type, short_type)
    level_display = get_level_display(short_level)
    text = f"<b>Работа над ошибками</b>\nТип: {display_name}\nУровень: {level_display}\n\nЗаданий на исправление: {len(error_ids)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Учебный режим", callback_data="reading_back_to_mode")],
        [InlineKeyboardButton(text="Сбросить ошибки", callback_data="reading_clear_errors")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ---------- Остальные обработчики ----------
@router.callback_query(ReadingStates.in_progress, F.data == "reading_back_to_mode")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_back_to_mode")
async def back_to_learning_mode(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0, session_correct=0, session_wrong=0)
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = callback.from_user.id
    await update_progress_message(callback.message, user_id, short_type, short_level, state)
    await render_task_message(callback.message, state, user_id, short_type, short_level, data.get("index", 0), paragraph_idx=0, is_revision=False)
    await callback.answer()

@router.callback_query(ReadingStates.in_progress, F.data == "reading_reset")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_reset")
@router.message(Command("reset_progress"))
async def reading_reset(event, state: FSMContext):
    if isinstance(event, CallbackQuery):
        message = event.message
        answer_func = event.answer
        current_state = await state.get_state()
        if current_state not in (ReadingStates.in_progress.state, ReadingStates.waiting_for_text.state):
            await answer_func("Сначала выберите тип и уровень в режиме чтения.", show_alert=True)
            return
        confirm_text = "Вы уверенны?\nВсе ошибки и правильные ответы будут обнулены. Задания будут даны с самого начала."
        await message.edit_text(confirm_text, reply_markup=get_reset_confirmation_keyboard(), parse_mode="HTML")
        if answer_func:
            await answer_func()
        return
    else:
        message = event
        current_state = await state.get_state()
        if current_state not in (ReadingStates.in_progress.state, ReadingStates.waiting_for_text.state):
            await message.answer("Сначала выберите тип и уровень в режиме чтения.")
            return
        confirm_text = "Вы уверенны?\nВсе ошибки и правильные ответы будут обнулены. Задания будут даны с самого начала."
        await message.answer(confirm_text, reply_markup=get_reset_confirmation_keyboard())

@router.callback_query(ReadingStates.in_progress, F.data == "reading_confirm_reset")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_confirm_reset")
async def confirm_reset(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")

    if not short_type or not short_level:
        await callback.answer("Не удалось определить режим.", show_alert=True)
        return

    await clear_all_keyboards(callback.message, state)

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    level_key = make_type_key(type_json, level_json)

    await reset_user_stats(user_id, type_json, level_json)
    await clear_reading_errors(user_id, type_json, level_json)
    await reset_progress_index(user_id, type_json, level_json)

    tasks = get_tasks_by_type_and_level(type_json, level_json)
    if tasks:
        new_order = list(range(len(tasks)))
        random.shuffle(new_order)
        await set_random_order(user_id, level_key, new_order)
        content_str = json.dumps(tasks, sort_keys=True, ensure_ascii=False)
        new_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
        await set_order_hash(user_id, level_key, new_hash)
        await state.update_data(shuffled_order=new_order)
    else:
        await state.update_data(shuffled_order=[])

    await state.update_data(index=0, paragraph_idx=0, is_revision=False, error_list=[], error_index=0,
                            revision_correct=0, revision_wrong=0, session_correct=0, session_wrong=0)

    await callback.message.edit_text("Прогресс сброшен. Все задания даны с начала.")
    await update_progress_message(callback.message, user_id, short_type, short_level, state)
    await render_task_message(callback.message, state, user_id, short_type, short_level, 0, paragraph_idx=0, is_revision=False)
    await callback.answer()

@router.callback_query(ReadingStates.in_progress, F.data == "reading_cancel_reset")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_cancel_reset")
async def cancel_reset(callback: CallbackQuery):
    await callback.message.edit_text("Сброс отменён. Продолжайте тренировку.")
    await callback.answer()

# ---------- ЗАВЕРШЕНИЕ СЕССИИ ----------
@router.callback_query(ReadingStates.in_progress, F.data == "reading_finish_session")
@router.callback_query(ReadingStates.waiting_for_text, F.data == "reading_finish_session")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = callback.from_user.id
    is_revision = data.get("is_revision", False)

    await clear_all_keyboards(callback.message, state)

    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)
    errors = await get_reading_errors(user_id, type_json, level_json)
    remaining_errors = len(errors)

    if is_revision:
        total_errors = data.get("total_errors_start", 0)
        rev_correct = data.get("revision_correct", 0)
        rev_wrong = data.get("revision_wrong", 0)

        if rev_correct == 0 and rev_wrong == 0:
            summary = "Вы не исправили ни одной ошибки."
        elif remaining_errors == 0:
            summary = "🎉 Вы исправили все ошибки!"
        else:
            summary = f"Вы исправили: {rev_correct} из {total_errors}. Осталось ошибок: {remaining_errors}."

        await callback.message.answer(summary)
        await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0,
                                session_correct=0, session_wrong=0)
        await update_progress_message(callback.message, user_id, short_type, short_level, state)
        await render_task_message(callback.message, state, user_id, short_type, short_level, data.get("index", 0), paragraph_idx=0, is_revision=False)
        await callback.answer()
        return

    total = session_correct + session_wrong
    if total == 0:
        text = "Сессия завершена 🙌🏻\nВы не ответили ни на одно задание."
    else:
        text = f"Сессия завершена 🙌🏽\n✔️ Правильно: {session_correct}\n✖️ Ошибок: {session_wrong}"

    await callback.message.answer(text)

    from .start import show_main_menu
    await show_main_menu(callback.message, edit=False)

    await state.clear()
    await callback.answer()

# ---------- Перехват любых команд ----------
@router.message(F.text.startswith('/'), ReadingStates.in_progress)
@router.message(F.text.startswith('/'), ReadingStates.waiting_for_text)
async def handle_any_command_in_reading(message: Message, state: FSMContext):
    await clear_all_keyboards(message, state)
    await message.answer("Практика завершена.")
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(message, edit=False)

# ---------- Обработка текста "Главное меню" ----------
@router.message(F.text == "🏠 Главное меню", ReadingStates.in_progress)
@router.message(F.text == "🏠 Главное меню", ReadingStates.waiting_for_text)
async def handle_main_menu_text(message: Message, state: FSMContext):
    await clear_all_keyboards(message, state)
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(message, edit=False)

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()

def normalize_answer(text: str) -> str:
    text = text.strip().lower()
    while text and text[-1] in ".,!?;:":
        text = text[:-1]
    return text.strip()