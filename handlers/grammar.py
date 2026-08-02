from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from data.users import get_user_state, set_user_state
from utils.db import (
    get_grammar_index, set_grammar_index, reset_grammar_index,
    get_grammar_stats, update_grammar_stats, reset_grammar_stats,
    add_grammar_error, remove_grammar_error, get_grammar_errors, clear_grammar_errors,
    reset_grammar_progress
)
import json
import re
from typing import List, Dict, Any

router = Router()

# ---------- Состояния ----------
class GrammarStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_for_text = State()
    in_progress = State()

# Путь к файлу с заданиями
TASKS_FILE = "data/grammar_tasks.json"

def load_tasks() -> Dict[str, List[Dict]]:
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

RAW_TASKS = load_tasks()

# Разбиваем задания на уровни
def split_into_levels(task_list: List[Dict]) -> Dict[str, List[Dict]]:
    total = len(task_list)
    if total == 0:
        return {"Новичок": [], "Любитель": [], "Эксперт": []}
    third = total // 3
    if third == 0:
        return {"Новичок": task_list, "Любитель": [], "Эксперт": []}
    return {
        "Новичок": task_list[:third],
        "Любитель": task_list[third:2*third],
        "Эксперт": task_list[2*third:]
    }

TASKS_BY_TYPE_LEVEL = {}
for task_type, tasks in RAW_TASKS.items():
    TASKS_BY_TYPE_LEVEL[task_type] = split_into_levels(tasks)

TASK_TYPES = list(TASKS_BY_TYPE_LEVEL.keys())
LEVELS = ["Новичок", "Любитель", "Эксперт"]

TYPE_EMOJIS = {
    "раскрытие_скобок": "📑",
    "вставка_пропусков": "↪️",
    "to_be_выбор": "⚖️",
    "to_be_скобки": "🗞️",
    "добавьте_s": "➕",
    "множественное_число": "🖇️",
    "единственное_число": "📎",
    "отрицание": "➖"
}

LEVEL_EMOJIS = {
    "Новичок": "🌱",
    "Любитель": "📚",
    "Эксперт": "🎓"
}

# ---------- Словари коротких кодов (для callback_data) ----------
SHORT_TYPE = {
    "раскрытие_скобок": "rsk",
    "вставка_пропусков": "vst",
    "to_be_выбор": "tbv",
    "to_be_скобки": "tbs",
    "добавьте_s": "ads",
    "множественное_число": "mn",
    "единственное_число": "ed",
    "отрицание": "otr"
}
LONG_TYPE = {v: k for k, v in SHORT_TYPE.items()}

SHORT_LEVEL = {
    "Новичок": "nov",
    "Любитель": "lyb",
    "Эксперт": "exp"
}
LONG_LEVEL = {v: k for k, v in SHORT_LEVEL.items()}

def make_type_key(task_type: str) -> str:
    return f"grammar_{task_type}"

def get_tasks(task_type: str, level: str) -> List[Dict]:
    return TASKS_BY_TYPE_LEVEL.get(task_type, {}).get(level, [])

# ----- Клавиатуры -----
def get_type_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for t in TASK_TYPES:
        emoji = TYPE_EMOJIS.get(t, "")
        short = SHORT_TYPE[t]
        buttons.append([InlineKeyboardButton(text=f"{emoji} {t}", callback_data=f"grammar_type_{short}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="grammar_back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_keyboard(task_type: str) -> InlineKeyboardMarkup:
    buttons = []
    short_type = SHORT_TYPE[task_type]
    for level in LEVELS:
        emoji = LEVEL_EMOJIS.get(level, "")
        short_level = SHORT_LEVEL[level]
        buttons.append([InlineKeyboardButton(text=f"{emoji} {level}", callback_data=f"grammar_level_{short_type}_{short_level}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="grammar_back_to_types")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_progress_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="grammar_revision")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="grammar_reset")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_keyboard(short_type: str, short_level: str, index: int, is_revision: bool = False) -> InlineKeyboardMarkup:
    rev_flag = "rev" if is_revision else "norm"
    buttons = [
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"grammar_show_answer:{short_type}:{short_level}:{index}:{rev_flag}"),
            InlineKeyboardButton(text="Завершить", callback_data="grammar_finish_session")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_reset_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Да, сбросить", callback_data="grammar_confirm_reset")],
        [InlineKeyboardButton(text="Назад", callback_data="grammar_cancel_reset")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_clear_errors_confirmation_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Да, сбросить ошибки", callback_data="grammar_confirm_clear_errors")],
        [InlineKeyboardButton(text="Назад", callback_data="grammar_cancel_clear_errors")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ----- Вспомогательные функции -----
def extract_instruction_and_task(question: str) -> tuple:
    """Разделяет вопрос на инструкцию и собственно задание."""
    lines = question.split('\n', 1)
    if len(lines) > 1:
        instruction = lines[0].strip()
        task_text = lines[1].strip()
    else:
        match = re.match(r'^(.+?)[:\.]\s*(.*)$', question, re.DOTALL)
        if match:
            instruction = match.group(1).strip()
            task_text = match.group(2).strip()
        else:
            instruction = "Выполните задание:"
            task_text = question
    return instruction, task_text

# ----- Отправка сообщений -----
async def send_or_update_progress(
    bot: Bot,
    chat_id: int,
    user_id: int,
    short_type: str,
    short_level: str,
    task: Dict,
    msg_id: int = None,
    edit: bool = False
) -> int:
    """Отправляет или обновляет сообщение с прогрессом."""
    type_key = make_type_key(short_type)
    level_key = short_level
    correct, wrong = await get_grammar_stats(user_id, type_key, level_key)
    errors = await get_grammar_errors(user_id, type_key, level_key)

    display_type = f"{TYPE_EMOJIS.get(short_type, '')} {short_type}"
    display_level = f"{LEVEL_EMOJIS.get(short_level, '')} {short_level}"

    instruction, _ = extract_instruction_and_task(task['question'])

    text = f"<b>Режим:</b> {display_type}\n"
    text += f"<b>Уровень:</b> {display_level}\n\n"
    text += f"{instruction}\n\n"
    text += f"<b>Ваш прогресс:</b>\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {len(errors)}"

    keyboard = get_progress_keyboard()

    if edit and msg_id:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return msg_id
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return sent.message_id

async def send_or_update_task(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    user_id: int,
    short_type: str,
    short_level: str,
    index: int = 0,
    task_id: int = None,
    is_revision: bool = False,
    msg_id: int = None,
    edit: bool = False
) -> int:
    """Отправляет или обновляет сообщение с заданием и кнопками."""
    if task_id is not None:
        tasks = get_tasks(short_type, short_level)
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            await bot.send_message(chat_id, "Задание не найдено.")
            return None
    else:
        tasks = get_tasks(short_type, short_level)
        if index >= len(tasks):
            index = 0
        task = tasks[index] if tasks else None

    if not task:
        await bot.send_message(chat_id, "Заданий для этого типа и уровня пока нет.")
        return None

    await state.update_data(
        short_type=short_type,
        short_level=short_level,
        current_index=index,
        current_task_id=task.get("id"),
        is_revision=is_revision,
        actual_task=task
    )

    _, task_text = extract_instruction_and_task(task['question'])

    # Используем короткие коды в callback_data
    short_type_code = SHORT_TYPE[short_type]
    short_level_code = SHORT_LEVEL[short_level]
    keyboard = get_task_keyboard(short_type_code, short_level_code, index, is_revision)

    if edit and msg_id:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=task_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        if task.get("input_type") == "text":
            await state.set_state(GrammarStates.waiting_for_text)
        else:
            await state.set_state(GrammarStates.in_progress)
        return msg_id
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=task_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        if task.get("input_type") == "text":
            await state.set_state(GrammarStates.waiting_for_text)
        else:
            await state.set_state(GrammarStates.in_progress)
        return sent.message_id

# ----- Вход в режим -----
async def enter_grammar_mode(message: Message, user_id: int, edit: bool = False, state: FSMContext = None):
    if state:
        await state.set_state(GrammarStates.choosing_type)
    text = "🔀 Грамматика\n\nВыберите тип задания:"
    keyboard = get_type_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)

# ----- Обработчики -----
@router.callback_query(F.data == "start_grammar")
async def start_grammar(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)

@router.callback_query(F.data == "grammar_back_to_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    from handlers.main import show_main_menu
    await show_main_menu(callback.message, edit=True)

@router.callback_query(GrammarStates.choosing_type, F.data == "grammar_back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)

@router.callback_query(GrammarStates.choosing_type, F.data.startswith("grammar_type_"))
async def select_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    short_code = callback.data.replace("grammar_type_", "")
    task_type = LONG_TYPE.get(short_code)
    if not task_type:
        await callback.message.answer("Ошибка: неизвестный тип.")
        return
    await state.set_state(GrammarStates.choosing_level)
    text = "Выберите уровень сложности:"
    keyboard = get_level_keyboard(task_type)
    await callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(GrammarStates.choosing_level, F.data.startswith("grammar_level_"))
async def choose_level(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = callback.data[len("grammar_level_"):]
    parts = data.split("_")
    if len(parts) != 2:
        await callback.message.answer("Ошибка в данных. Попробуйте ещё раз.")
        return
    short_type_code, short_level_code = parts[0], parts[1]
    short_type = LONG_TYPE.get(short_type_code)
    short_level = LONG_LEVEL.get(short_level_code)
    if not short_type or not short_level:
        await callback.message.answer("Ошибка: неизвестный тип или уровень.")
        return

    user_id = callback.from_user.id

    tasks = get_tasks(short_type, short_level)
    if not tasks:
        await callback.message.answer(
            "Заданий для этого типа и уровня пока нет. Выберите другой уровень.",
            reply_markup=get_level_keyboard(short_type)
        )
        return

    type_key = make_type_key(short_type)
    index = await get_grammar_index(user_id, type_key, short_level)
    if index >= len(tasks):
        index = 0
        await set_grammar_index(user_id, type_key, short_level, index)

    await state.update_data(
        short_type=short_type,
        short_level=short_level,
        current_index=index,
        is_revision=False,
        session_correct=0,
        session_wrong=0,
        progress_msg_id=None,
        task_msg_id=None
    )

    bot = callback.bot
    chat_id = callback.message.chat.id

    task = tasks[index]

    progress_msg_id = await send_or_update_progress(
        bot, chat_id, user_id, short_type, short_level, task, edit=False
    )
    task_msg_id = await send_or_update_task(
        bot, chat_id, state, user_id, short_type, short_level, index, is_revision=False, edit=False
    )

    await state.update_data(progress_msg_id=progress_msg_id, task_msg_id=task_msg_id)

    await callback.message.delete()

# ----- Обработка ответов (кнопки) -----
@router.callback_query(GrammarStates.in_progress, F.data.startswith("grammar_answer:"))
@router.callback_query(GrammarStates.waiting_for_text, F.data.startswith("grammar_answer:"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 6:
        await callback.answer("Ошибка формата")
        return
    short_type_code, short_level_code, index_str, chosen_idx_str, mode = parts[1], parts[2], parts[3], parts[4], parts[5]
    short_type = LONG_TYPE.get(short_type_code)
    short_level = LONG_LEVEL.get(short_level_code)
    if not short_type or not short_level:
        await callback.answer("Ошибка: неизвестный тип или уровень.")
        return
    index = int(index_str)
    chosen_idx = int(chosen_idx_str)
    is_revision = (mode == "rev")
    user_id = callback.from_user.id

    tasks = get_tasks(short_type, short_level)
    if index >= len(tasks):
        await callback.answer("Задание не найдено")
        return
    task = tasks[index]
    correct = (chosen_idx == task.get("correct", -1))

    type_key = make_type_key(short_type)
    level_key = short_level

    data = await state.get_data()
    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)

    if is_revision:
        if correct:
            await remove_grammar_error(user_id, type_key, level_key, task["id"])
            await update_grammar_stats(user_id, type_key, level_key, True)
            session_correct += 1
            await state.update_data(session_correct=session_correct)
        else:
            session_wrong += 1
            await state.update_data(session_wrong=session_wrong)
    else:
        if correct:
            await update_grammar_stats(user_id, type_key, level_key, True)
            session_correct += 1
            await state.update_data(session_correct=session_correct)
            await remove_grammar_error(user_id, type_key, level_key, task["id"])
        else:
            await update_grammar_stats(user_id, type_key, level_key, False)
            session_wrong += 1
            await state.update_data(session_wrong=session_wrong)
            await add_grammar_error(user_id, type_key, level_key, task["id"])

    task_msg_id = data.get("task_msg_id")
    if task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=task_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    if correct:
        result_text = "Правильно!"
    else:
        options = task.get("options", [])
        correct_idx = task.get("correct", -1)
        if 0 <= correct_idx < len(options):
            correct_text = options[correct_idx]
        else:
            correct_text = str(correct_idx)
        result_text = f"Неправильно. Правильный ответ: {correct_text}"

    await callback.message.answer(result_text)

    if not is_revision:
        next_index = index + 1
        if next_index >= len(tasks):
            next_index = 0
        await set_grammar_index(user_id, type_key, level_key, next_index)
        await state.update_data(current_index=next_index)

        progress_msg_id = data.get("progress_msg_id")
        await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            short_type,
            short_level,
            tasks[next_index],
            msg_id=progress_msg_id,
            edit=True
        )

        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            user_id,
            short_type,
            short_level,
            next_index,
            is_revision=False,
            msg_id=task_msg_id,
            edit=True
        )
        await state.update_data(task_msg_id=new_task_msg_id)

    else:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await callback.message.answer("🎉 Вы исправили все ошибки! Возвращаемся в учебный режим.")
            await state.update_data(is_revision=False)
            current_index = await get_grammar_index(user_id, type_key, level_key)
            if current_index >= len(tasks):
                current_index = 0
            progress_msg_id = data.get("progress_msg_id")
            await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                short_type,
                short_level,
                tasks[current_index],
                msg_id=progress_msg_id,
                edit=True
            )
            new_task_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                short_level,
                current_index,
                is_revision=False,
                msg_id=task_msg_id,
                edit=True
            )
            await state.update_data(task_msg_id=new_task_msg_id)
        else:
            next_error_id = errors[0]
            progress_msg_id = data.get("progress_msg_id")
            await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                short_type,
                short_level,
                task,
                msg_id=progress_msg_id,
                edit=True
            )
            new_task_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                short_level,
                task_id=next_error_id,
                is_revision=True,
                msg_id=task_msg_id,
                edit=True
            )
            await state.update_data(task_msg_id=new_task_msg_id)

    await callback.answer()

# ----- Обработка текстовых ответов -----
@router.message(GrammarStates.waiting_for_text, F.text)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    index = data.get("current_index", 0)
    is_revision = data.get("is_revision", False)
    task = data.get("actual_task")
    if not task:
        await message.answer("Задание не найдено. Попробуйте выбрать уровень заново.")
        await state.clear()
        return

    user_id = message.from_user.id
    type_key = make_type_key(short_type)
    level_key = short_level

    def normalize(s):
        s = s.strip().lower()
        if s.endswith('.'):
            s = s[:-1]
        return s

    correct_answer = task.get("correct")
    user_input = message.text.strip()
    if isinstance(correct_answer, list):
        user_clean = normalize(user_input)
        correct_clean = [normalize(str(ans)) for ans in correct_answer]
        correct = user_clean in correct_clean
    else:
        user_clean = normalize(user_input)
        correct_clean = normalize(str(correct_answer))
        correct = (user_clean == correct_clean)

    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)

    if is_revision:
        if correct:
            await remove_grammar_error(user_id, type_key, level_key, task["id"])
            await update_grammar_stats(user_id, type_key, level_key, True)
            session_correct += 1
            await state.update_data(session_correct=session_correct)
        else:
            session_wrong += 1
            await state.update_data(session_wrong=session_wrong)
    else:
        if correct:
            await update_grammar_stats(user_id, type_key, level_key, True)
            session_correct += 1
            await state.update_data(session_correct=session_correct)
            await remove_grammar_error(user_id, type_key, level_key, task["id"])
        else:
            await update_grammar_stats(user_id, type_key, level_key, False)
            session_wrong += 1
            await state.update_data(session_wrong=session_wrong)
            await add_grammar_error(user_id, type_key, level_key, task["id"])

    if correct:
        result_text = "Правильно!"
    else:
        if isinstance(correct_answer, list):
            correct_text = " или ".join(correct_answer)
        else:
            correct_text = str(correct_answer)
        result_text = f"Неправильно. Правильный ответ: {correct_text}"

    await message.answer(result_text)

    tasks = get_tasks(short_type, short_level)
    if not is_revision:
        next_index = index + 1
        if next_index >= len(tasks):
            next_index = 0
        await set_grammar_index(user_id, type_key, level_key, next_index)
        await state.update_data(current_index=next_index)

        progress_msg_id = data.get("progress_msg_id")
        await send_or_update_progress(
            message.bot,
            message.chat.id,
            user_id,
            short_type,
            short_level,
            tasks[next_index],
            msg_id=progress_msg_id,
            edit=True
        )

        task_msg_id = data.get("task_msg_id")
        new_task_msg_id = await send_or_update_task(
            message.bot,
            message.chat.id,
            state,
            user_id,
            short_type,
            short_level,
            next_index,
            is_revision=False,
            msg_id=task_msg_id,
            edit=True
        )
        await state.update_data(task_msg_id=new_task_msg_id)
    else:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await message.answer("🎉 Вы исправили все ошибки! Возвращаемся в учебный режим.")
            await state.update_data(is_revision=False)
            current_index = await get_grammar_index(user_id, type_key, level_key)
            if current_index >= len(tasks):
                current_index = 0
            progress_msg_id = data.get("progress_msg_id")
            await send_or_update_progress(
                message.bot,
                message.chat.id,
                user_id,
                short_type,
                short_level,
                tasks[current_index],
                msg_id=progress_msg_id,
                edit=True
            )
            task_msg_id = data.get("task_msg_id")
            new_task_msg_id = await send_or_update_task(
                message.bot,
                message.chat.id,
                state,
                user_id,
                short_type,
                short_level,
                current_index,
                is_revision=False,
                msg_id=task_msg_id,
                edit=True
            )
            await state.update_data(task_msg_id=new_task_msg_id)
        else:
            next_error_id = errors[0]
            progress_msg_id = data.get("progress_msg_id")
            await send_or_update_progress(
                message.bot,
                message.chat.id,
                user_id,
                short_type,
                short_level,
                task,
                msg_id=progress_msg_id,
                edit=True
            )
            task_msg_id = data.get("task_msg_id")
            new_task_msg_id = await send_or_update_task(
                message.bot,
                message.chat.id,
                state,
                user_id,
                short_type,
                short_level,
                task_id=next_error_id,
                is_revision=True,
                msg_id=task_msg_id,
                edit=True
            )
            await state.update_data(task_msg_id=new_task_msg_id)

# ----- Показать ответ -----
@router.callback_query(GrammarStates.in_progress, F.data.startswith("grammar_show_answer:"))
@router.callback_query(GrammarStates.waiting_for_text, F.data.startswith("grammar_show_answer:"))
async def show_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("Ошибка формата")
        return
    short_type_code, short_level_code, index_str, mode = parts[1], parts[2], parts[3], parts[4]
    short_type = LONG_TYPE.get(short_type_code)
    short_level = LONG_LEVEL.get(short_level_code)
    if not short_type or not short_level:
        await callback.answer("Ошибка: неизвестный тип или уровень.")
        return
    index = int(index_str)
    is_revision = (mode == "rev")
    user_id = callback.from_user.id

    tasks = get_tasks(short_type, short_level)
    if index >= len(tasks):
        await callback.answer("Задание не найдено")
        return
    task = tasks[index]
    correct_answer = task.get("correct")
    if isinstance(correct_answer, list):
        correct_text = " или ".join(correct_answer)
    else:
        correct_text = str(correct_answer)

    data = await state.get_data()
    task_msg_id = data.get("task_msg_id")
    if task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=task_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    await callback.message.answer(f"Правильный ответ: {correct_text}")

    type_key = make_type_key(short_type)
    level_key = short_level

    if is_revision:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await callback.message.answer("🎉 Вы исправили все ошибки! Возвращаемся в учебный режим.")
            await state.update_data(is_revision=False)
            current_index = await get_grammar_index(user_id, type_key, level_key)
            if current_index >= len(tasks):
                current_index = 0
            progress_msg_id = data.get("progress_msg_id")
            await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                short_type,
                short_level,
                tasks[current_index],
                msg_id=progress_msg_id,
                edit=True
            )
            task_msg_id = data.get("task_msg_id")
            new_task_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                short_level,
                current_index,
                is_revision=False,
                msg_id=task_msg_id,
                edit=True
            )
            await state.update_data(task_msg_id=new_task_msg_id)
        else:
            next_error_id = errors[0]
            progress_msg_id = data.get("progress_msg_id")
            await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                short_type,
                short_level,
                task,
                msg_id=progress_msg_id,
                edit=True
            )
            task_msg_id = data.get("task_msg_id")
            new_task_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                short_level,
                task_id=next_error_id,
                is_revision=True,
                msg_id=task_msg_id,
                edit=True
            )
            await state.update_data(task_msg_id=new_task_msg_id)
    else:
        next_index = index + 1
        if next_index >= len(tasks):
            next_index = 0
        await set_grammar_index(user_id, type_key, level_key, next_index)
        await state.update_data(current_index=next_index)

        progress_msg_id = data.get("progress_msg_id")
        await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            short_type,
            short_level,
            tasks[next_index],
            msg_id=progress_msg_id,
            edit=True
        )

        task_msg_id = data.get("task_msg_id")
        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            user_id,
            short_type,
            short_level,
            next_index,
            is_revision=False,
            msg_id=task_msg_id,
            edit=True
        )
        await state.update_data(task_msg_id=new_task_msg_id)

    await callback.answer()

# ----- Работа над ошибками -----
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_revision")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_revision")
async def grammar_revision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    if not short_type or not short_level:
        await callback.message.answer("Сначала выберите тип и уровень.")
        return

    type_key = make_type_key(short_type)
    level_key = short_level
    errors = await get_grammar_errors(user_id, type_key, level_key)
    if not errors:
        await callback.message.answer("🎉 Ошибок нет! Отличная работа.")
        return

    await state.update_data(is_revision=True)
    task_id = errors[0]
    tasks = get_tasks(short_type, short_level)
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        await callback.message.answer("Задание с ошибкой не найдено.")
        return

    progress_msg_id = data.get("progress_msg_id")
    await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        short_level,
        task,
        msg_id=progress_msg_id,
        edit=True
    )

    task_msg_id = data.get("task_msg_id")
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        short_level,
        task_id=task_id,
        is_revision=True,
        msg_id=task_msg_id,
        edit=True
    )
    await state.update_data(task_msg_id=new_task_msg_id)

# ----- Сброс прогресса -----
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_reset")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_reset")
async def grammar_reset_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    confirm_text = (
        "Вы уверены, что хотите сбросить весь прогресс для текущего типа и уровня?\n"
        "Статистика, ошибки и текущее задание будут обнулены.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(confirm_text, reply_markup=get_reset_confirmation_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "grammar_confirm_reset")
async def grammar_confirm_reset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    if not short_type or not short_level:
        await callback.message.answer("Ошибка: не выбран тип или уровень.")
        return

    type_key = make_type_key(short_type)
    level_key = short_level
    await reset_grammar_progress(user_id, type_key, level_key)
    await set_grammar_index(user_id, type_key, level_key, 0)

    await state.update_data(is_revision=False, session_correct=0, session_wrong=0)

    tasks = get_tasks(short_type, short_level)
    if not tasks:
        await callback.message.answer("Заданий для этого уровня нет.")
        return

    progress_msg_id = data.get("progress_msg_id")
    await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        short_level,
        tasks[0],
        msg_id=progress_msg_id,
        edit=True
    )

    task_msg_id = data.get("task_msg_id")
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        short_level,
        0,
        is_revision=False,
        msg_id=task_msg_id,
        edit=True
    )
    await state.update_data(task_msg_id=new_task_msg_id)

    try:
        await callback.message.delete()
    except Exception:
        pass

@router.callback_query(F.data == "grammar_cancel_reset")
async def grammar_cancel_reset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    if short_type and short_level:
        tasks = get_tasks(short_type, short_level)
        index = data.get("current_index", 0)
        if index >= len(tasks):
            index = 0
        task = tasks[index]
        progress_msg_id = data.get("progress_msg_id")
        await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            callback.from_user.id,
            short_type,
            short_level,
            task,
            msg_id=progress_msg_id,
            edit=True
        )
        task_msg_id = data.get("task_msg_id")
        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            callback.from_user.id,
            short_type,
            short_level,
            index,
            is_revision=data.get("is_revision", False),
            msg_id=task_msg_id,
            edit=True
        )
        await state.update_data(task_msg_id=new_task_msg_id)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)

# ----- Завершение сессии -----
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_finish_session")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_finish_session")
async def grammar_finish_session(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    if not short_type or not short_level:
        await callback.message.answer("Ошибка: не выбран тип или уровень.")
        return

    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)

    type_key = make_type_key(short_type)
    level_key = short_level
    errors = await get_grammar_errors(user_id, type_key, level_key)
    remaining_errors = len(errors)

    if session_correct == 0 and session_wrong == 0 and remaining_errors == 0:
        text = "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
    else:
        text = "Сессия завершена! 🙌🏻\n"
        if session_correct > 0 or session_wrong > 0:
            text += f"✔️ Правильно: {session_correct}\n"
            text += f"✖️ Ошибок: {session_wrong}\n"
        if remaining_errors > 0:
            text += f"Осталось ошибок: {remaining_errors}\n"
        else:
            text += "Все ошибки исправлены! 🎉\n"

    await callback.message.answer(text)

    from handlers.main import show_main_menu
    await show_main_menu(callback.message, edit=False)

    await state.clear()
    await callback.answer()

@router.message(GrammarStates.waiting_for_text, F.voice)
@router.message(GrammarStates.in_progress, F.voice)
async def ignore_voice_in_grammar(message: Message, state: FSMContext):
    await message.answer("Голосовые сообщения не поддерживаются в этом режиме. Пожалуйста, используйте кнопки или текстовый ввод.")

# ----- Сброс ошибок -----
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_clear_errors")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_clear_errors")
async def grammar_clear_errors_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    confirm_text = (
        "Вы уверены, что хотите сбросить все ошибки?\n"
        "Все задания с ошибками будут удалены. Вы сможете начать их заново.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(confirm_text, reply_markup=get_clear_errors_confirmation_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "grammar_confirm_clear_errors")
async def grammar_confirm_clear_errors(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    if not short_type or not short_level:
        await callback.message.answer("Ошибка: не выбран тип или уровень.")
        return
    type_key = make_type_key(short_type)
    level_key = short_level
    await clear_grammar_errors(user_id, type_key, level_key)

    await callback.message.edit_text("Список ошибок очищен. Продолжайте тренировку.")
    await state.update_data(is_revision=False)

    tasks = get_tasks(short_type, short_level)
    index = await get_grammar_index(user_id, type_key, level_key)
    if index >= len(tasks):
        index = 0

    progress_msg_id = data.get("progress_msg_id")
    await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        short_level,
        tasks[index] if tasks else {},
        msg_id=progress_msg_id,
        edit=True
    )
    task_msg_id = data.get("task_msg_id")
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        short_level,
        index,
        is_revision=False,
        msg_id=task_msg_id,
        edit=True
    )
    await state.update_data(task_msg_id=new_task_msg_id)
    await callback.answer()

@router.callback_query(F.data == "grammar_cancel_clear_errors")
async def grammar_cancel_clear_errors(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    if short_type and short_level:
        tasks = get_tasks(short_type, short_level)
        index = data.get("current_index", 0)
        if index >= len(tasks):
            index = 0
        progress_msg_id = data.get("progress_msg_id")
        await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            callback.from_user.id,
            short_type,
            short_level,
            tasks[index] if tasks else {},
            msg_id=progress_msg_id,
            edit=True
        )
        task_msg_id = data.get("task_msg_id")
        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            callback.from_user.id,
            short_type,
            short_level,
            index,
            is_revision=data.get("is_revision", False),
            msg_id=task_msg_id,
            edit=True
        )
        await state.update_data(task_msg_id=new_task_msg_id)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)