import logging
import random
import json
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
    clear_reading_errors_db as clear_reading_errors
)
from utils.redis_utils import (
    get_global_welcome_index,
    get_user_progress,
    set_user_progress,
    reset_user_progress,
    get_redis
)
from states.reading_states import ReadingStates
from data.users import get_user_state, set_user_state

logger = logging.getLogger(__name__)
router = Router()

READING_WELCOME_MESSAGES = [
    "<b>📖 Чтение</b>\n\n<i>Чтение — это ключ к расширению словарного запаса и пониманию структур языка. Регулярно читайте тексты разного уровня и учитесь выделять главное.</i>\n\nВыберите тип задания и уровень — и тренируйтесь в удобном темпе.",
    "<b>📖 Чтение</b>\n\n<i>Умение быстро читать и понимать текст пригодится в любом контексте: от экзаменов до работы. Начните с коротких текстов и постепенно увеличивайте сложность.</i>\n\nГотовы попробовать?",
    "<b>📖 Чтение</b>\n\n<i>Чтение на английском — это не только полезно, но и увлекательно. Выбирайте задания, которые вам интересны, и прокачивайте навык.</i>\n\nКакой тип выберете сегодня?",
    "<b>📖 Чтение</b>\n\n<i>Навык чтения включает в себя понимание деталей, поиск информации и интерпретацию текста. Тренируйте все аспекты с нашими заданиями.</i>\n\nПриступим?",
    "<b>📖 Чтение</b>\n\n<i>Читайте, анализируйте, отвечайте на вопросы — и вы заметите, как тексты становятся понятнее с каждым разом.</i>\n\nВыберите задание и уровень."
]

TYPE_DISPLAY = {
    "podbor": "🥈 Подбор заголовка",
    "truefalse": "⚖️ True/False/Not stated",
    "choice": "☑️ Вопросы с выбором ответа",
    "order": "📄 Восстановление порядка абзацев",
    "random": "🎲 Случайный тип"
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
    "random": "выполните задание"
}

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
        [InlineKeyboardButton(text="Да, сбросить ошибки", callback_data="reading_confirm_clear_errors")],
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

# ---------- Случайный тип ----------
async def get_all_tasks_for_random(level: str):
    all_items = []
    level_json = LEVEL_MAP.get(level, level)
    for type_key in TYPE_MAP.keys():
        type_json = TYPE_MAP[type_key]
        if type_json in TASKS:
            if isinstance(TASKS[type_json], dict):
                tasks = TASKS[type_json].get(level_json, [])
                for t in tasks:
                    all_items.append({"task": t, "type_key": type_key})
            elif isinstance(TASKS[type_json], list):
                tasks = [t for t in TASKS[type_json] if t.get("level") == level_json]
                for t in tasks:
                    all_items.append({"task": t, "type_key": type_key})
    return all_items

async def get_random_order(user_id: int, level: str):
    r = await get_redis()
    key = f"random_order:{user_id}:{level}"
    order_data = await r.get(key)
    if order_data:
        return json.loads(order_data)
    all_items = await get_all_tasks_for_random(level)
    if not all_items:
        return []
    random.shuffle(all_items)
    order_ids = [item["task"]["id"] for item in all_items]
    await r.set(key, json.dumps(order_ids))
    return order_ids

async def get_task_by_id(user_id: int, level: str, task_id: int):
    all_items = await get_all_tasks_for_random(level)
    for item in all_items:
        if item["task"]["id"] == task_id:
            return item["task"], item["type_key"]
    return None, None

def normalize_answer(text: str) -> str:
    text = text.strip().lower()
    while text and text[-1] in ".,!?;:":
        text = text[:-1]
    return text.strip()

# ---------- Отправка задания ----------
async def render_task_message(message: Message, state: FSMContext, user_id: int, short_type: str, short_level: str, index: int, paragraph_idx: int = 0, is_revision: bool = False):
    await clear_task_keyboard(message, state)

    # Определяем задание
    if short_type == "random":
        order = await get_random_order(user_id, short_level)
        if not order:
            await message.answer("Нет заданий для этого уровня.")
            return None, None
        if index >= len(order):
            index = 0
        task_id = order[index]
        task, actual_type = await get_task_by_id(user_id, short_level, task_id)
        if not task:
            await message.answer("Задание не найдено.")
            return None, None
        await state.update_data(actual_type=actual_type, actual_task=task, random_index=index)
        actual_type = actual_type
    else:
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = get_task(type_json, level_json, index)
        if not task:
            return None, None
        await state.update_data(actual_type=short_type, actual_task=task)
        actual_type = short_type

    paragraphs = task.get("paragraphs", [])
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    if not paragraphs:
        paragraphs = ["(текст отсутствует)"]

    if short_type == "random":
        type_label = TYPE_DISPLAY.get(actual_type, actual_type)
        text = f"<b>Тип задания:</b> {type_label}\n\n"
    else:
        text = ""

    if actual_type == "order":
        for i, para in enumerate(paragraphs):
            if not para.startswith(chr(65+i) + ")"):
                text += f"{chr(65+i)}) {para}\n\n"
            else:
                text += f"{para}\n\n"
        text += f"{task.get('question', '')}"
    else:
        if actual_type == "truefalse":
            text += f"{paragraphs[0]}\n\n"
            text += f"{task.get('statement', '')}\n\nВыберите верное утверждение:"
        else:
            text += f"{paragraphs[0]}\n\n"
            text += f"{task.get('question', '')}\n"

    is_text_input = task.get("input_type") == "text"

    if actual_type == "order":
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

    # Управление состоянием FSM
    if is_text_input:
        await state.set_state(ReadingStates.waiting_for_text)
    else:
        # Для кнопочных заданий – держим in_progress
        await state.set_state(ReadingStates.in_progress)

    return text, keyboard

# ---------- Общая статистика ----------
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

# ---------- Отправка прогресса (редактирование) ----------
async def send_progress_message_edit(message: Message, user_id: int, short_type: str, short_level: str, state: FSMContext):
    if short_type == "random":
        correct, _ = await get_total_stats(user_id, short_level)
        error_count = 0
        for t in TYPE_MAP.keys():
            t_json = TYPE_MAP[t]
            level_json = LEVEL_MAP.get(short_level, short_level)
            errors = await get_reading_errors(user_id, t_json, level_json)
            error_count += len(errors)
        display_name = "🎲 Случайный тип"
        level_display = get_level_display(short_level)
        description = TYPE_DESCRIPTION.get("random", "выполните задание")
    else:
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
    sent_msg = await message.edit_text(text, reply_markup=get_progress_keyboard(), parse_mode="HTML")
    await state.update_data(progress_msg_id=sent_msg.message_id)
    return sent_msg

# -------------------- Обработчики --------------------
@router.callback_query(F.data == "start_reading")
async def start_reading(callback: CallbackQuery, state: FSMContext):
    await clear_all_keyboards(callback.message, state)
    global_idx = await get_global_welcome_index()
    welcome_text = READING_WELCOME_MESSAGES[global_idx]
    await callback.message.edit_text(welcome_text, reply_markup=get_type_choice_keyboard(), parse_mode="HTML")
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

    if short_type == "random":
        all_items = await get_all_tasks_for_random(short_level)
        if not all_items:
            await callback.message.edit_text("Задания для этого уровня пока отсутствуют. Попробуйте другой уровень.")
            await callback.answer()
            return
        order = await get_random_order(user_id, short_level)
        index = await get_user_progress(user_id, "random", short_level)
        if index >= len(order):
            index = 0
            await set_user_progress(user_id, "random", short_level, index)
    else:
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        index = await get_user_progress(user_id, type_json, level_json)
        task = get_task(type_json, level_json, index)
        if not task:
            index = 0
            await set_user_progress(user_id, type_json, level_json, index)
            task = get_task(type_json, level_json, index)
            if not task:
                await callback.message.edit_text("Задания для этого уровня пока отсутствуют. Попробуйте другой уровень.")
                await callback.answer()
                return

    await state.update_data(
        short_type=short_type,
        short_level=short_level,
        index=index,
        paragraph_idx=0,
        is_revision=False,
        error_list=[],
        error_index=0,
        last_task_msg_id=None,
        revision_correct=0,
        revision_wrong=0,
        session_correct=0,
        session_wrong=0,
        progress_msg_id=None
    )

    # Устанавливаем основное состояние in_progress (всегда активно в режиме чтения)
    await state.set_state(ReadingStates.in_progress)

    await send_progress_message_edit(callback.message, user_id, short_type, short_level, state)
    await render_task_message(callback.message, state, user_id, short_type, short_level, index, paragraph_idx=0, is_revision=False)
    await callback.answer()

# ---------- Обработка ответов (кнопки) ----------
@router.callback_query(F.data.startswith("reading_answer:"))
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
    if short_type == "random":
        actual_type = data.get("actual_type")
        if not actual_type:
            await callback.answer("Ошибка: не удалось определить тип задания")
            return
        type_json = TYPE_MAP.get(actual_type, actual_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = data.get("actual_task")
        if not task:
            await callback.answer("Задание не найдено")
            return
    else:
        actual_type = short_type
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = get_task(type_json, level_json, index)
        if not task:
            await callback.answer("Задание не найдено")
            return

    correct = (chosen_idx == task["correct"])

    if is_revision:
        if correct:
            await remove_reading_error(user_id, type_json, level_json, index)
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
            logger.info(f"✅ Correct: user={user_id}, type={type_json}, level={level_json}")
        else:
            await update_user_stats(user_id, type_json, level_json, False)
            await add_reading_error(user_id, type_json, level_json, index)
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data(session_wrong=session_wrong)
            logger.info(f"❌ Wrong: user={user_id}, type={type_json}, level={level_json} -> добавлена ошибка")

    await callback.message.edit_reply_markup(reply_markup=None)

    if correct:
        result_text = "Правильно!"
    else:
        correct_text = task['options'][task['correct']]
        if short_type == "order" or actual_type == "order":
            explanation = task.get("explanation", "")
            if explanation:
                result_text = f"Неправильно. Правильный ответ: {correct_text}\n\n{explanation}"
            else:
                result_text = f"Неправильно. Правильный ответ: {correct_text}"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct_text}"
    await callback.message.answer(result_text)

    # Обновление индекса
    if short_type == "random":
        order = await get_random_order(user_id, short_level)
        if order:
            next_index = index + 1
            if next_index >= len(order):
                next_index = 0
            await set_user_progress(user_id, "random", short_level, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        else:
            await callback.message.answer("Нет заданий для этого уровня.")
            await callback.answer()
            return
    else:
        next_index = index + 1
        next_task = get_task(type_json, level_json, next_index)
        if not next_task:
            next_index = 0
        await set_user_progress(user_id, type_json, level_json, next_index)
        await state.update_data(index=next_index, paragraph_idx=0)

    # Переход к следующему заданию
    if is_revision:
        if short_type == "random":
            error_ids = []
            for t in TYPE_MAP.keys():
                t_json = TYPE_MAP[t]
                errors = await get_reading_errors(user_id, t_json, level_json)
                error_ids.extend(errors)
            error_ids = list(set(error_ids))
        else:
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
            await show_next_task(callback.message, state, is_revision=False)
            await callback.answer()
            return
        else:
            await show_revision_task(callback.message, state, error_ids)
            await callback.answer()
            return
    else:
        await render_task_message(callback.message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)
        await callback.answer()

# ---------- Обработка текстовых ответов (только когда состояние waiting_for_text) ----------
@router.message(ReadingStates.waiting_for_text, F.text, ~F.text.startswith('/'))
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    index = data.get("index")
    is_revision = data.get("is_revision", False)
    user_id = message.from_user.id

    if short_type == "random":
        actual_type = data.get("actual_type")
        if not actual_type:
            await message.answer("Ошибка: не удалось определить тип задания")
            return
        type_json = TYPE_MAP.get(actual_type, actual_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = data.get("actual_task")
        if not task:
            await message.answer("Задание не найдено")
            return
    else:
        actual_type = short_type
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = get_task(type_json, level_json, index)
        if not task:
            await message.answer("Задание не найдено.")
            return

    correct_answer = task.get("correct")
    user_input = message.text.strip()

    if isinstance(correct_answer, list):
        user_parts = [normalize_answer(p) for p in user_input.split(";") if p.strip()]
        correct_parts = [normalize_answer(p) for p in correct_answer]
        correct = (user_parts == correct_parts)
    else:
        user_clean = normalize_answer(user_input)
        correct_clean = normalize_answer(str(correct_answer))
        correct = (user_clean == correct_clean)

    if is_revision:
        if correct:
            await remove_reading_error(user_id, type_json, level_json, index)
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
        else:
            await update_user_stats(user_id, type_json, level_json, False)
            await add_reading_error(user_id, type_json, level_json, index)
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
        if short_type == "order" or actual_type == "order":
            explanation = task.get("explanation", "")
            if explanation:
                result_text = f"Неправильно. Правильный ответ: {correct_text}\n\n{explanation}"
            else:
                result_text = f"Неправильно. Правильный ответ: {correct_text}"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct_text}"
    await message.answer(result_text)

    # Возвращаем состояние обратно на in_progress (уже не ждём текст)
    await state.set_state(ReadingStates.in_progress)

    # Обновление индекса
    if short_type == "random":
        order = await get_random_order(user_id, short_level)
        if order:
            next_index = index + 1
            if next_index >= len(order):
                next_index = 0
            await set_user_progress(user_id, "random", short_level, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        else:
            await message.answer("Нет заданий для этого уровня.")
            return
    else:
        next_index = index + 1
        next_task = get_task(type_json, level_json, next_index)
        if not next_task:
            next_index = 0
        await set_user_progress(user_id, type_json, level_json, next_index)
        await state.update_data(index=next_index, paragraph_idx=0)

    if is_revision:
        if short_type == "random":
            error_ids = []
            for t in TYPE_MAP.keys():
                t_json = TYPE_MAP[t]
                errors = await get_reading_errors(user_id, t_json, level_json)
                error_ids.extend(errors)
            error_ids = list(set(error_ids))
        else:
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
            await show_next_task(message, state, is_revision=False)
            return
        else:
            await show_revision_task(message, state, error_ids)
            return
    else:
        await render_task_message(message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)

# ---------- Игнорирование голосовых (но они уже блокируются middleware, оставляем на всякий случай) ----------
@router.message(F.voice)
async def ignore_voice(message: Message, state: FSMContext):
    # Этот обработчик не сработает, если middleware блокирует,
    # но оставляем для дополнительной защиты
    current_state = await state.get_state()
    if current_state and current_state.startswith("ReadingStates"):
        await message.answer("Голосовые сообщения не поддерживаются в этом режиме. Пожалуйста, используйте кнопки или текстовый ввод.")

# ---------- Вспомогательные функции ----------
async def show_next_task(message: Message, state: FSMContext, is_revision: bool):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    index = data.get("index", 0)
    user_id = message.from_user.id

    if not is_revision:
        await render_task_message(message, state, user_id, short_type, short_level, index, paragraph_idx=0, is_revision=False)

async def show_revision_task(message: Message, state: FSMContext, error_ids: list):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = message.from_user.id

    if not error_ids:
        await message.answer("Нет заданий для исправления.")
        return

    if short_type == "random":
        random.shuffle(error_ids)
        task_id = error_ids[0]
        task, actual_type = await get_task_by_id(user_id, short_level, task_id)
        if not task:
            await message.answer("Не удалось найти задание для исправления.")
            return
        await state.update_data(actual_type=actual_type, actual_task=task)
        await render_task_message(message, state, user_id, actual_type, short_level, task_id, paragraph_idx=0, is_revision=True)
        await state.update_data(index=task_id, paragraph_idx=0, is_revision=True, error_list=error_ids, error_index=0)
    else:
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task_id = error_ids[0]
        await render_task_message(message, state, user_id, short_type, short_level, task_id, paragraph_idx=0, is_revision=True)
        await state.update_data(index=task_id, paragraph_idx=0, is_revision=True, error_list=error_ids, error_index=0)

@router.callback_query(F.data.startswith("reading_show_answer:"))
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

    if short_type == "random":
        actual_type = data.get("actual_type")
        if not actual_type:
            await callback.answer("Ошибка: не удалось определить тип задания")
            return
        type_json = TYPE_MAP.get(actual_type, actual_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = data.get("actual_task")
        if not task:
            await callback.answer("Задание не найдено")
            return
    else:
        actual_type = short_type
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = get_task(type_json, level_json, index)
        if not task:
            await callback.answer("Задание не найдено")
            return

    await callback.message.edit_reply_markup(reply_markup=None)

    correct = task.get("correct")

    if short_type == "order" or actual_type == "order":
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
        if short_type == "random":
            error_ids = []
            for t in TYPE_MAP.keys():
                t_json = TYPE_MAP[t]
                errors = await get_reading_errors(user_id, t_json, level_json)
                error_ids.extend(errors)
            error_ids = list(set(error_ids))
        else:
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
            if short_type == "random":
                order = await get_random_order(user_id, short_level)
                if order:
                    next_index = (index + 1) % len(order)
                    await set_user_progress(user_id, "random", short_level, next_index)
                    await state.update_data(index=next_index, paragraph_idx=0)
            else:
                next_index = index + 1
                next_task = get_task(type_json, level_json, next_index)
                if not next_task:
                    next_index = 0
                await set_user_progress(user_id, type_json, level_json, next_index)
                await state.update_data(index=next_index, paragraph_idx=0)
            await show_next_task(callback.message, state, is_revision=False)
        else:
            try:
                cur_pos = error_ids.index(index)
            except ValueError:
                cur_pos = -1
            if cur_pos != -1 and cur_pos + 1 < len(error_ids):
                next_error_id = error_ids[cur_pos + 1]
                await show_revision_task(callback.message, state, [next_error_id])
            else:
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
                if short_type == "random":
                    order = await get_random_order(user_id, short_level)
                    if order:
                        next_index = (index + 1) % len(order)
                        await set_user_progress(user_id, "random", short_level, next_index)
                        await state.update_data(index=next_index, paragraph_idx=0)
                else:
                    next_index = index + 1
                    next_task = get_task(type_json, level_json, next_index)
                    if not next_task:
                        next_index = 0
                    await set_user_progress(user_id, type_json, level_json, next_index)
                    await state.update_data(index=next_index, paragraph_idx=0)
                await show_next_task(callback.message, state, is_revision=False)
    else:
        if short_type == "random":
            order = await get_random_order(user_id, short_level)
            if order:
                next_index = (index + 1) % len(order)
                await set_user_progress(user_id, "random", short_level, next_index)
                await state.update_data(index=next_index, paragraph_idx=0)
            else:
                await callback.message.answer("Нет заданий для этого уровня.")
                await callback.answer()
                return
        else:
            next_index = index + 1
            next_task = get_task(type_json, level_json, next_index)
            if not next_task:
                next_index = 0
            await set_user_progress(user_id, type_json, level_json, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        await render_task_message(callback.message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)

    await callback.answer()

@router.callback_query(F.data == "reading_revision")
@router.message(Command("revision_mode"))
async def reading_revision(event, state: FSMContext):
    if isinstance(event, CallbackQuery):
        user_id = event.from_user.id
        message = event.message
        answer_func = event.answer
    else:
        user_id = event.from_user.id
        message = event
        answer_func = None

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

    if short_type == "random":
        error_ids = []
        for t in TYPE_MAP.keys():
            t_json = TYPE_MAP[t]
            errors = await get_reading_errors(user_id, t_json, level_json)
            error_ids.extend(errors)
        error_ids = list(set(error_ids))
    else:
        error_ids = await get_reading_errors(user_id, type_json, level_json)

    if not error_ids:
        text = "🎉 Ошибок нет! Отличная работа."
        if answer_func:
            await answer_func(text, show_alert=True)
        else:
            await message.answer(text)
        return

    await state.update_data(
        is_revision=True,
        error_list=error_ids,
        error_index=0,
        revision_correct=0,
        revision_wrong=0,
        session_correct=0,
        session_wrong=0
    )

    text = f"<b>Режим - Работа над ошибками.</b>\n\nКол-во ошибок: {len(error_ids)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сбросить ошибки", callback_data="reading_clear_errors")],
        [InlineKeyboardButton(text="Учебный режим", callback_data="reading_back_to_mode")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await show_revision_task(message, state, error_ids)
    if answer_func:
        await answer_func()

# ---------- Подтверждение сброса ошибок ----------
@router.callback_query(F.data == "reading_clear_errors")
async def clear_errors_confirm(callback: CallbackQuery, state: FSMContext):
    confirm_text = (
        "Вы уверены, что хотите сбросить все ошибки?\n"
        "Все задания с ошибками будут удалены. Вы сможете начать их заново.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(
        confirm_text,
        reply_markup=get_clear_errors_confirmation_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "reading_confirm_clear_errors")
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

    if short_type == "random":
        for t in TYPE_MAP.keys():
            t_json = TYPE_MAP[t]
            await clear_reading_errors(user_id, t_json, level_json)
    else:
        await clear_reading_errors(user_id, type_json, level_json)

    await callback.message.edit_text("Список ошибок очищен. Возвращаемся в учебный режим.")
    await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0, session_correct=0, session_wrong=0)
    await show_next_task(callback.message, state, is_revision=False)
    await callback.answer()

@router.callback_query(F.data == "reading_cancel_clear_errors")
async def cancel_clear_errors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = callback.from_user.id

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)

    if short_type == "random":
        error_ids = []
        for t in TYPE_MAP.keys():
            t_json = TYPE_MAP[t]
            errors = await get_reading_errors(user_id, t_json, level_json)
            error_ids.extend(errors)
        error_ids = list(set(error_ids))
    else:
        error_ids = await get_reading_errors(user_id, type_json, level_json)

    text = f"<b>Режим - Работа над ошибками.</b>\n\nКол-во ошибок: {len(error_ids)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сбросить ошибки", callback_data="reading_clear_errors")],
        [InlineKeyboardButton(text="Учебный режим", callback_data="reading_back_to_mode")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ---------- Остальные обработчики ----------
@router.callback_query(F.data == "reading_back_to_mode")
async def back_to_learning_mode(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Возвращаемся в учебный режим.")
    await state.update_data(is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0, session_correct=0, session_wrong=0)
    await show_next_task(callback.message, state, is_revision=False)
    await callback.answer()

@router.callback_query(F.data == "reading_reset")
@router.message(Command("reset_progress"))
async def reading_reset(event, state: FSMContext):
    if isinstance(event, CallbackQuery):
        message = event.message
        answer_func = event.answer
    else:
        message = event
        answer_func = None

    confirm_text = (
        "Вы уверены? Ошибки и правильные задания будут обнулены.\n"
        "Все упражнения будут даны с самого начала."
    )
    await message.answer(confirm_text, reply_markup=get_reset_confirmation_keyboard())
    if answer_func:
        await answer_func()

@router.callback_query(F.data == "reading_confirm_reset")
async def confirm_reset(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")

    if not short_type or not short_level:
        await callback.answer("Не удалось определить режим.", show_alert=True)
        return

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)

    if short_type == "random":
        for t in TYPE_MAP.keys():
            t_json = TYPE_MAP[t]
            await reset_user_progress(user_id, t_json, level_json)
            await clear_reading_errors(user_id, t_json, level_json)
            await reset_user_stats(user_id, t_json, level_json)
        await reset_user_progress(user_id, "random", short_level)
        r = await get_redis()
        await r.delete(f"random_order:{user_id}:{short_level}")
    else:
        await reset_user_progress(user_id, type_json, level_json)
        await clear_reading_errors(user_id, type_json, level_json)
        await reset_user_stats(user_id, type_json, level_json)

    await state.update_data(index=0, paragraph_idx=0, is_revision=False, error_list=[], error_index=0, revision_correct=0, revision_wrong=0, session_correct=0, session_wrong=0)

    await callback.message.edit_text("Прогресс сброшен. Все упражнения будут даны с самого начала.")
    await send_progress_message_edit(callback.message, user_id, short_type, short_level, state)
    await show_next_task(callback.message, state, is_revision=False)
    await callback.answer()

@router.callback_query(F.data == "reading_cancel_reset")
async def cancel_reset(callback: CallbackQuery):
    await callback.message.edit_text("Сброс отменён. Продолжайте тренировку.")
    await callback.answer()

@router.callback_query(F.data == "reading_finish_session")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = callback.from_user.id

    await clear_all_keyboards(callback.message, state)

    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)

    if short_type == "random":
        remaining_errors = 0
        for t in TYPE_MAP.keys():
            t_json = TYPE_MAP[t]
            level_json = LEVEL_MAP.get(short_level, short_level)
            errors = await get_reading_errors(user_id, t_json, level_json)
            remaining_errors += len(errors)
    else:
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        errors = await get_reading_errors(user_id, type_json, level_json)
        remaining_errors = len(errors)

    if session_correct == 0 and session_wrong == 0 and remaining_errors == 0:
        text = "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
    else:
        text = "Сессия завершена! 🙌🏻\n"
        if session_correct > 0:
            text += f"Исправлено: {session_correct}\n"
        if remaining_errors > 0:
            text += f"Осталось ошибок: {remaining_errors}\n"
        else:
            text += "Все ошибки исправлены! 🎉\n"

    await callback.message.answer(text)

    from .start import show_main_menu
    await show_main_menu(callback.message, edit=False)

    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()