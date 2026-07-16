import logging
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from data.reading_loader import get_task, TASKS
from utils.redis_utils import (
    get_global_welcome_index,
    get_user_progress,
    set_user_progress,
    get_user_stats,
    update_user_stats,
    reset_user_progress,
    add_reading_error,
    remove_reading_error,
    get_reading_errors,
    clear_reading_errors
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

def get_type_choice_keyboard():
    buttons = []
    for key, label in TYPE_DISPLAY.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"reading_type:{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_keyboard(short_type: str):
    buttons = [
        [InlineKeyboardButton(text="🌱 Новичок", callback_data=f"reading_level:{short_type}:beginner")],
        [InlineKeyboardButton(text="📚 Любитель", callback_data=f"reading_level:{short_type}:intermediate")],
        [InlineKeyboardButton(text="🎓 Эксперт", callback_data=f"reading_level:{short_type}:expert")],
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

async def clear_keyboard(message: Message, state: FSMContext):
    data = await state.get_data()
    last_id = data.get("last_task_msg_id")
    if last_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=last_id, reply_markup=None)
        except Exception:
            pass
    await state.update_data(last_task_msg_id=None)

async def get_all_tasks_for_random(level: str):
    all_tasks = []
    level_json = LEVEL_MAP.get(level, level)
    for type_key in TYPE_MAP.keys():
        type_json = TYPE_MAP[type_key]
        tasks = TASKS.get(type_json, {}).get(level_json, [])
        all_tasks.extend(tasks)
    return all_tasks

async def render_task_message(message: Message, state: FSMContext, user_id: int, short_type: str, short_level: str, index: int, paragraph_idx: int = 0, is_revision: bool = False):
    # Убираем старую клавиатуру и сбрасываем флаг ошибки для нового задания
    await clear_keyboard(message, state)
    await state.update_data(was_wrong=False)

    if short_type == "random":
        all_tasks = await get_all_tasks_for_random(short_level)
        if not all_tasks:
            await message.answer("Нет заданий для этого уровня.")
            return None, None
        if index >= len(all_tasks):
            index = 0
        task = all_tasks[index]
        actual_type_key = None
        for key, json_key in TYPE_MAP.items():
            if json_key in task.get("type", ""):
                actual_type_key = key
                break
        if not actual_type_key:
            actual_type_key = "choice"
        await state.update_data(actual_type=actual_type_key, actual_task=task, random_index=index)
        actual_type = actual_type_key
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

    if actual_type == "order":
        text = ""
        for i, para in enumerate(paragraphs):
            if not para.startswith(chr(65+i) + ")"):
                text += f"{chr(65+i)}) {para}\n\n"
            else:
                text += f"{para}\n\n"
        text += f"{task.get('question', '')}"
        keyboard = get_action_keyboard(short_type, short_level, index, is_revision)
        sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(last_task_msg_id=sent_msg.message_id)
        return text, keyboard

    if paragraph_idx >= len(paragraphs):
        paragraph_idx = 0
    current_paragraph = paragraphs[paragraph_idx]

    text = f"{current_paragraph}\n\n"
    text += f"{task.get('question', '')}\n"

    if task.get("input_type") == "text":
        text += "Введите ответ в чат.\n"
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
    return text, keyboard

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

async def send_progress_message(callback: CallbackQuery, short_type: str, short_level: str):
    user_id = callback.from_user.id
    if short_type == "random":
        correct, wrong = await get_total_stats(user_id, short_level)
        display_name = "🎲 Случайный тип"
    else:
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        correct, wrong = await get_user_stats(user_id, type_json, level_json)
        display_name = TYPE_DISPLAY.get(short_type, short_type)
    text = f"<b>Режим: {display_name}</b>\n\n"
    text += "Внимательно прочитайте текст и выполните задание.\n\n"
    text += f"Ваш прогресс:\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {wrong}\n\n"
    text += "/revision_mode — работа над ошибками\n"
    text += "/reset_progress — сбросить прогресс"
    await callback.message.answer(text, reply_markup=get_progress_keyboard(), parse_mode="HTML")

# -------------------- Обработчики --------------------
@router.callback_query(F.data == "start_reading")
async def start_reading(callback: CallbackQuery, state: FSMContext):
    await clear_keyboard(callback.message, state)
    global_idx = await get_global_welcome_index()
    welcome_text = READING_WELCOME_MESSAGES[global_idx]
    await callback.message.edit_text(welcome_text, reply_markup=get_type_choice_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "reading_back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await clear_keyboard(callback.message, state)
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
        index = await get_user_progress(user_id, "random", short_level)
        all_tasks = await get_all_tasks_for_random(short_level)
        if not all_tasks:
            await callback.message.edit_text("Задания для этого уровня пока отсутствуют. Попробуйте другой уровень.")
            await callback.answer()
            return
        if index >= len(all_tasks):
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
        was_wrong=False
    )

    await send_progress_message(callback, short_type, short_level)
    await render_task_message(callback.message, state, user_id, short_type, short_level, index, paragraph_idx=0, is_revision=False)
    await state.set_state(ReadingStates.waiting_for_text)
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
    else:
        if correct:
            await update_user_stats(user_id, type_json, level_json, True)
            await state.update_data(was_wrong=False)
        else:
            await update_user_stats(user_id, type_json, level_json, False)
            await add_reading_error(user_id, type_json, level_json, index)
            await state.update_data(was_wrong=True)

    await callback.message.edit_reply_markup(reply_markup=None)

    if correct:
        result_text = "Правильно!"
    else:
        correct_text = task['options'][task['correct']]
        result_text = f"Неправильно. Правильный ответ: {correct_text}"
    await callback.message.answer(result_text)

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
            await callback.message.answer("🎉 Все ошибки исправлены! Возвращаемся в обычный режим.")
            await state.update_data(is_revision=False, error_list=[], error_index=0)
            await show_next_task(callback.message, state, is_revision=False)
            await callback.answer()
            return
        else:
            await show_revision_task(callback.message, state, error_ids)
            await callback.answer()
            return
    else:
        if short_type == "random":
            all_tasks = await get_all_tasks_for_random(short_level)
            if not all_tasks:
                await callback.message.answer("Нет заданий для этого уровня.")
                await callback.answer()
                return
            next_index = index + 1
            if next_index >= len(all_tasks):
                next_index = 0
            await set_user_progress(user_id, "random", short_level, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        else:
            next_index = index + 1
            next_task = get_task(type_json, level_json, next_index)
            if not next_task:
                next_index = 0
            await set_user_progress(user_id, type_json, level_json, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        await render_task_message(callback.message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)
        await callback.answer()

# ---------- Обработка текстовых ответов ----------
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
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = get_task(type_json, level_json, index)
        if not task:
            await message.answer("Задание не найдено.")
            return

    correct_answer = task.get("correct")
    user_input = message.text.strip()

    if isinstance(correct_answer, list):
        user_parts = [p.strip().lower() for p in user_input.split(";") if p.strip()]
        correct_parts = [p.strip().lower() for p in correct_answer]
        correct = (user_parts == correct_parts)
    else:
        user_clean = "".join(user_input.split()).lower()
        correct_clean = "".join(str(correct_answer).split()).lower()
        correct = (user_clean == correct_clean)

    if is_revision:
        if correct:
            await remove_reading_error(user_id, type_json, level_json, index)
            await update_user_stats(user_id, type_json, level_json, True)
    else:
        if correct:
            await update_user_stats(user_id, type_json, level_json, True)
            await state.update_data(was_wrong=False)
        else:
            await update_user_stats(user_id, type_json, level_json, False)
            await add_reading_error(user_id, type_json, level_json, index)
            await state.update_data(was_wrong=True)

    await clear_keyboard(message, state)

    if correct:
        result_text = "Правильно!"
    else:
        if isinstance(correct_answer, list):
            correct_text = '; '.join(correct_answer)
        else:
            correct_text = str(correct_answer)
        result_text = f"Неправильно. Правильный ответ: {correct_text}"
    await message.answer(result_text)

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
            await message.answer("🎉 Все ошибки исправлены! Возвращаемся в обычный режим.")
            await state.update_data(is_revision=False, error_list=[], error_index=0)
            await show_next_task(message, state, is_revision=False)
            return
        else:
            await show_revision_task(message, state, error_ids)
            return
    else:
        if short_type == "random":
            all_tasks = await get_all_tasks_for_random(short_level)
            if not all_tasks:
                await message.answer("Нет заданий для этого уровня.")
                return
            next_index = index + 1
            if next_index >= len(all_tasks):
                next_index = 0
            await set_user_progress(user_id, "random", short_level, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        else:
            next_index = index + 1
            next_task = get_task(type_json, level_json, next_index)
            if not next_task:
                next_index = 0
            await set_user_progress(user_id, type_json, level_json, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        await render_task_message(message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)

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
        task_id = error_ids[0]
        found_type = None
        for t in TYPE_MAP.keys():
            t_json = TYPE_MAP[t]
            tasks_for_type = TASKS.get(t_json, {})
            for level, tasks in tasks_for_type.items():
                for task in tasks:
                    if task.get("id") == task_id:
                        found_type = t
                        break
                if found_type:
                    break
            if found_type:
                break
        if not found_type:
            await message.answer("Не удалось определить тип задания для исправления.")
            return
        await state.update_data(actual_type=found_type)
        await render_task_message(message, state, user_id, found_type, short_level, task_id, paragraph_idx=0, is_revision=True)
        await state.update_data(index=task_id, paragraph_idx=0, is_revision=True, error_list=error_ids, error_index=0)
    else:
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task_id = error_ids[0]
        await render_task_message(message, state, user_id, short_type, short_level, task_id, paragraph_idx=0, is_revision=True)
        await state.update_data(index=task_id, paragraph_idx=0, is_revision=True, error_list=error_ids, error_index=0)

# ---------- Показать ответ ----------
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
        type_json = TYPE_MAP.get(short_type, short_type)
        level_json = LEVEL_MAP.get(short_level, short_level)
        task = get_task(type_json, level_json, index)
        if not task:
            await callback.answer("Задание не найдено")
            return

    await callback.message.edit_reply_markup(reply_markup=None)

    correct = task.get("correct")
    was_wrong = data.get("was_wrong", False)

    # Формируем правильный ответ
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
        # Если была ошибка и есть пояснение — показываем его
        if was_wrong:
            explanation = task.get("explanation", "")
            if explanation:
                await callback.message.answer(f"Правильный ответ: {correct_text}\n\nОбъяснение: {explanation}")
            else:
                await callback.message.answer(f"Правильный ответ: {correct_text}")
        else:
            await callback.message.answer(f"Правильный ответ: {correct_text}")
    else:
        if "options" in task and correct < len(task["options"]):
            correct_text = task["options"][correct]
        else:
            correct_text = str(correct)
        await callback.message.answer(f"Правильный ответ: {correct_text}")

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
            await callback.message.answer("🎉 Все ошибки исправлены! Возвращаемся в обычный режим.")
            await state.update_data(is_revision=False, error_list=[], error_index=0)
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
                await callback.message.answer("🎉 Все ошибки просмотрены! Возвращаемся в обычный режим.")
                await state.update_data(is_revision=False, error_list=[], error_index=0)
                await show_next_task(callback.message, state, is_revision=False)
    else:
        if short_type == "random":
            all_tasks = await get_all_tasks_for_random(short_level)
            if not all_tasks:
                await callback.message.answer("Нет заданий для этого уровня.")
                await callback.answer()
                return
            next_index = index + 1
            if next_index >= len(all_tasks):
                next_index = 0
            await set_user_progress(user_id, "random", short_level, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        else:
            next_index = index + 1
            next_task = get_task(type_json, level_json, next_index)
            if not next_task:
                next_index = 0
            await set_user_progress(user_id, type_json, level_json, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
        await render_task_message(callback.message, state, user_id, short_type, short_level, next_index, paragraph_idx=0, is_revision=False)

    await callback.answer()

# ---------- Работа над ошибками (кнопка и команда) ----------
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

    # Всегда вычисляем type_json и level_json из short_type и short_level
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

    await state.update_data(is_revision=True, error_list=error_ids, error_index=0)
    await show_revision_task(message, state, error_ids)
    if answer_func:
        await answer_func()

# ---------- Сброс прогресса ----------
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
        await reset_user_progress(user_id, "random", short_level)
    else:
        await reset_user_progress(user_id, type_json, level_json)
        await clear_reading_errors(user_id, type_json, level_json)

    await state.update_data(index=0, paragraph_idx=0, is_revision=False, error_list=[], error_index=0)

    await callback.message.edit_text("Прогресс сброшен. Все упражнения будут даны с самого начала.")

    if short_type == "random":
        correct, wrong = await get_total_stats(user_id, short_level)
        display_name = "🎲 Случайный тип"
    else:
        correct, wrong = await get_user_stats(user_id, type_json, level_json)
        display_name = TYPE_DISPLAY.get(short_type, short_type)
    text = f"<b>Режим: {display_name}</b>\n\n"
    text += "Внимательно прочитайте текст и выполните задание.\n\n"
    text += f"Ваш прогресс:\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {wrong}\n\n"
    text += "/revision_mode — работа над ошибками\n"
    text += "/reset_progress — сбросить прогресс"
    await callback.message.answer(text, reply_markup=get_progress_keyboard(), parse_mode="HTML")

    await show_next_task(callback.message, state, is_revision=False)
    await callback.answer()

@router.callback_query(F.data == "reading_cancel_reset")
async def cancel_reset(callback: CallbackQuery):
    await callback.message.edit_text("Сброс отменён. Продолжайте тренировку.")
    await callback.answer()

# ---------- Завершение сессии ----------
@router.callback_query(F.data == "reading_finish_session")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    user_id = callback.from_user.id

    await clear_keyboard(callback.message, state)

    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)

    if short_type == "random":
        correct, wrong = await get_total_stats(user_id, short_level)
    else:
        correct, wrong = await get_user_stats(user_id, type_json, level_json)

    total = correct + wrong
    if total == 0:
        text = "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
    else:
        accuracy = (correct / total * 100)
        text = f"Сессия завершена! 🙌🏻\nПравильно: {correct}\nОшибок: {wrong}\nТочность: {accuracy:.1f}%"

    await callback.message.answer(text)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    from .start import show_main_menu
    await show_main_menu(callback.message, edit=False)

    await state.clear()
    await callback.answer()

# ---------- Игнорирование ----------
@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()