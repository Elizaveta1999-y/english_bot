from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import or_f
from data.users import get_user_state, set_user_state
from utils.db import (
    get_grammar_index, set_grammar_index, reset_grammar_index,
    get_grammar_stats, update_grammar_stats, reset_grammar_stats,
    add_grammar_error, remove_grammar_error, get_grammar_errors, clear_grammar_errors,
    reset_grammar_progress,
    get_random_order, set_random_order
)
import json
import re
import random
import logging
from typing import List, Dict, Any

router = Router()
logger = logging.getLogger(__name__)

# ---------- Состояния ----------
class GrammarStates(StatesGroup):
    choosing_type = State()
    waiting_for_text = State()
    in_progress = State()

# ---------- Обработчик команд ----------
@router.message(
    F.text.startswith('/'),
    or_f(
        GrammarStates.choosing_type,
        GrammarStates.waiting_for_text,
        GrammarStates.in_progress
    )
)
async def handle_commands_in_grammar(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    task_msg_id = data.get("task_msg_id")
    if task_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=task_msg_id, reply_markup=None)
        except Exception:
            pass
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=progress_msg_id, reply_markup=None)
        except Exception:
            pass
    await message.answer("Практика завершена.")
    await state.clear()

# ---------- Обработчик не-текстовых сообщений ----------
@router.message(
    or_f(
        GrammarStates.in_progress,
        GrammarStates.waiting_for_text
    ),
    ~F.text
)
async def handle_non_text_in_grammar(message: Message, state: FSMContext):
    await message.answer("Введите текстовый ответ")

# ---------- Загрузка заданий ----------
TASKS_FILE = "data/grammar_tasks.json"

def load_tasks() -> Dict[str, List[Dict]]:
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

RAW_TASKS = load_tasks()
TASKS_BY_TYPE = {}
for task_type, tasks in RAW_TASKS.items():
    TASKS_BY_TYPE[task_type] = tasks

TASK_TYPES = list(TASKS_BY_TYPE.keys())

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

def make_type_key(task_type: str) -> str:
    return f"grammar_{task_type}"

def get_tasks(task_type: str) -> List[Dict]:
    return TASKS_BY_TYPE.get(task_type, [])

# ----- Клавиатуры -----
def get_type_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for t in TASK_TYPES:
        display_name = t.replace('_', ' ')
        emoji = TYPE_EMOJIS.get(t, "")
        short = SHORT_TYPE[t]
        buttons.append([InlineKeyboardButton(text=f"{emoji} {display_name}", callback_data=f"grammar_type_{short}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="grammar_back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_progress_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="grammar_revision")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="grammar_reset")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_keyboard(short_type: str, index: int, is_revision: bool = False) -> InlineKeyboardMarkup:
    rev_flag = "rev" if is_revision else "norm"
    buttons = [
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"grammar_show_answer:{short_type}:{index}:{rev_flag}"),
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

# ---------- Вспомогательные функции ----------
def extract_instruction_and_task(question: str) -> tuple:
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

# ---------- Функции для работы со случайным порядком ----------
async def get_or_create_order(user_id: int, short_type: str) -> List[int]:
    type_key = make_type_key(short_type)
    order = await get_random_order(user_id, type_key)
    if order is None:
        tasks = get_tasks(short_type)
        indices = list(range(len(tasks)))
        random.shuffle(indices)
        await set_random_order(user_id, type_key, indices)
        return indices
    else:
        if isinstance(order, str):
            try:
                order = json.loads(order)
            except:
                order = []
        return order

async def reset_order(user_id: int, short_type: str) -> List[int]:
    type_key = make_type_key(short_type)
    tasks = get_tasks(short_type)
    indices = list(range(len(tasks)))
    random.shuffle(indices)
    await set_random_order(user_id, type_key, indices)
    return indices

# ----- Отправка сообщений (ИСПРАВЛЕНА - НИКОГДА НЕ УДАЛЯЕТ) -----
async def send_or_update_progress(
    bot: Bot,
    chat_id: int,
    user_id: int,
    short_type: str,
    task: Dict,
    msg_id: int = None,
    edit: bool = False,
    is_revision: bool = False,
    errors_count: int = None
) -> int:
    """
    Отправляет или редактирует прогресс-сообщение.
    НИКОГДА не удаляет сообщение. Если редактирование не удаётся -
    просто возвращает старый msg_id без отправки нового.
    """
    type_key = make_type_key(short_type)
    correct, wrong = await get_grammar_stats(user_id, type_key, "all")
    errors = await get_grammar_errors(user_id, type_key, "all")
    errors_len = len(errors) if errors_count is None else errors_count

    display_type = f"{TYPE_EMOJIS.get(short_type, '')} {short_type.replace('_', ' ')}"

    if is_revision:
        text = f"<b>Работа над ошибками</b>\n"
        text += f"Тип: {display_type}\n\n"
        text += f"Заданий на исправление: {errors_len}\n"
        keyboard = None
    else:
        instruction, _ = extract_instruction_and_task(task['question'])
        if short_type == "раскрытие_скобок" and "впишите ответ" not in instruction:
            instruction = instruction.replace("Раскройте скобки.", "Раскройте скобки, впишите ответ (1–2 слова).")
        elif short_type == "отрицание":
            instruction = "Перепишите предложение в отрицательную форму"
        text = f"<b>Режим:</b> {display_type}\n\n"
        text += f"{instruction}\n\n"
        text += f"<b>Ваш прогресс:</b>\n"
        text += f"✔️ Правильно: {correct}\n"
        text += f"✖️ Ошибок: {errors_len}"
        keyboard = get_progress_keyboard()

    # Если нужно отредактировать и есть ID – пробуем отредактировать
    if edit and msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return msg_id
        except Exception as e:
            # Редактирование не удалось – НЕ УДАЛЯЕМ, НЕ ОТПРАВЛЯЕМ НОВОЕ
            logger.error(f"Не удалось отредактировать прогресс-сообщение {msg_id}: {e}")
            return msg_id  # возвращаем старый ID, не создавая новое сообщение
    else:
        # Отправляем новое сообщение (только если нет msg_id или edit=False)
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
    index: int = 0,
    task_id: int = None,
    is_revision: bool = False,
    msg_id: int = None
) -> int:
    """Отправляет или редактирует задание. Если msg_id передан – редактирует, иначе отправляет новое."""
    tasks = get_tasks(short_type)
    if task_id is not None:
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            await bot.send_message(chat_id, "Задание не найдено.")
            return None
    else:
        data = await state.get_data()
        order = data.get("order")
        if order is None:
            order = await get_or_create_order(user_id, short_type)
            await state.update_data(order=order)
        if index >= len(order):
            index = 0
        real_index = order[index]
        task = tasks[real_index] if real_index < len(tasks) else None
        if not task:
            await bot.send_message(chat_id, "Задание не найдено.")
            return None

    await state.update_data(
        short_type=short_type,
        current_index=index,
        current_task_id=task.get("id"),
        is_revision=is_revision,
        actual_task=task
    )

    _, task_text = extract_instruction_and_task(task['question'])
    short_type_code = SHORT_TYPE[short_type]
    callback_index = index if not is_revision else -1
    keyboard = get_task_keyboard(short_type_code, callback_index, is_revision)

    if msg_id:
        try:
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
        except Exception:
            # Если редактирование не удалось – удаляем старый msg и отправляем новый
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
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
        try:
            await message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await message.answer(text, reply_markup=keyboard)
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
    try:
        await show_main_menu(callback.message, edit=True)
    except Exception:
        await show_main_menu(callback.message, edit=False)

@router.callback_query(GrammarStates.choosing_type, F.data.startswith("grammar_type_"))
async def select_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    short_code = callback.data.replace("grammar_type_", "")
    short_type = LONG_TYPE.get(short_code)
    if not short_type:
        await callback.message.answer("Ошибка: неизвестный тип.")
        return

    user_id = callback.from_user.id
    tasks = get_tasks(short_type)
    if not tasks:
        await callback.message.answer("Заданий для этого типа пока нет.")
        return

    type_key = make_type_key(short_type)
    order = await get_or_create_order(user_id, short_type)
    index = await get_grammar_index(user_id, type_key, "all")
    if index >= len(order):
        index = 0
        await set_grammar_index(user_id, type_key, "all", index)

    await state.update_data(
        short_type=short_type,
        order=order,
        current_index=index,
        is_revision=False,
        session_correct=0,
        session_wrong=0,
        progress_msg_id=None,
        task_msg_id=None
    )

    bot = callback.bot
    chat_id = callback.message.chat.id
    real_index = order[index]
    task = tasks[real_index]

    progress_msg_id = await send_or_update_progress(
        bot, chat_id, user_id, short_type, task, msg_id=None, edit=False, is_revision=False
    )
    task_msg_id = await send_or_update_task(
        bot, chat_id, state, user_id, short_type, index, is_revision=False, msg_id=None
    )

    await state.update_data(progress_msg_id=progress_msg_id, task_msg_id=task_msg_id)
    await callback.message.delete()

# ----- Обработка ответов (кнопки) -----
@router.callback_query(GrammarStates.in_progress, F.data.startswith("grammar_answer:"))
@router.callback_query(GrammarStates.waiting_for_text, F.data.startswith("grammar_answer:"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("Ошибка формата")
        return
    short_type_code, index_str, chosen_idx_str, mode = parts[1], parts[2], parts[3], parts[4]
    short_type = LONG_TYPE.get(short_type_code)
    if not short_type:
        await callback.answer("Ошибка: неизвестный тип.")
        return
    index = int(index_str)
    chosen_idx = int(chosen_idx_str)
    is_revision = (mode == "rev")
    user_id = callback.from_user.id

    data = await state.get_data()
    order = data.get("order")
    if order is None or index >= len(order):
        await callback.answer("Ошибка порядка заданий")
        return
    real_index = order[index]
    tasks = get_tasks(short_type)
    if real_index >= len(tasks):
        await callback.answer("Задание не найдено")
        return
    task = tasks[real_index]
    correct = (chosen_idx == task.get("correct", -1))

    type_key = make_type_key(short_type)
    level_key = "all"
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

    # Убираем кнопки у текущего задания
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
        if next_index >= len(order):
            next_index = 0
        await set_grammar_index(user_id, type_key, level_key, next_index)
        await state.update_data(current_index=next_index)

        real_next = order[next_index]
        next_task = tasks[real_next]

        old_progress_id = data.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            short_type,
            next_task,
            msg_id=old_progress_id,
            edit=True,
            is_revision=False
        )
        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            user_id,
            short_type,
            next_index,
            is_revision=False,
            msg_id=None
        )
        await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)

    else:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await callback.message.answer("🎉 Вы исправили все ошибки!")
            await state.update_data(is_revision=False)
            order = await get_or_create_order(user_id, short_type)
            await state.update_data(order=order)
            current_index = await get_grammar_index(user_id, type_key, level_key)
            if current_index >= len(order):
                current_index = 0
            real_index = order[current_index]
            task = tasks[real_index]
            old_progress_id = data.get("progress_msg_id")
            new_progress_id = await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                short_type,
                task,
                msg_id=old_progress_id,
                edit=True,
                is_revision=False
            )
            new_task_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                current_index,
                is_revision=False,
                msg_id=None
            )
            await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
        else:
            correction_text = f"Вы исправили: {session_correct}\nОсталось ошибок: {len(errors)}"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Учебный режим", callback_data="grammar_back_to_learning")],
                [InlineKeyboardButton(text="Исправить ошибки", callback_data="grammar_revision_continue")]
            ])
            await callback.message.answer(correction_text, reply_markup=keyboard)

    await callback.answer()

# ----- Обработка текстовых ответов -----
@router.message(GrammarStates.waiting_for_text, F.text)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    index = data.get("current_index", 0)
    is_revision = data.get("is_revision", False)
    task = data.get("actual_task")
    if not task:
        await message.answer("Задание не найдено. Попробуйте выбрать тип заново.")
        await state.clear()
        return

    user_id = message.from_user.id
    type_key = make_type_key(short_type)
    level_key = "all"

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

    task_msg_id = data.get("task_msg_id")
    if task_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=task_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    if correct:
        result_text = "Правильно!"
    else:
        if isinstance(correct_answer, list):
            correct_text = " или ".join(correct_answer)
        else:
            correct_text = str(correct_answer)
        result_text = f"Неправильно. Правильный ответ: {correct_text}"

    await message.answer(result_text)

    tasks = get_tasks(short_type)
    order = data.get("order")
    if order is None:
        order = await get_or_create_order(user_id, short_type)
        await state.update_data(order=order)

    if not is_revision:
        next_index = index + 1
        if next_index >= len(order):
            next_index = 0
        await set_grammar_index(user_id, type_key, level_key, next_index)
        await state.update_data(current_index=next_index)

        real_next = order[next_index]
        next_task = tasks[real_next]

        old_progress_id = data.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            message.bot,
            message.chat.id,
            user_id,
            short_type,
            next_task,
            msg_id=old_progress_id,
            edit=True,
            is_revision=False
        )
        new_task_msg_id = await send_or_update_task(
            message.bot,
            message.chat.id,
            state,
            user_id,
            short_type,
            next_index,
            is_revision=False,
            msg_id=None
        )
        await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
    else:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await message.answer("🎉 Вы исправили все ошибки!")
            await state.update_data(is_revision=False)
            order = await get_or_create_order(user_id, short_type)
            await state.update_data(order=order)
            current_index = await get_grammar_index(user_id, type_key, level_key)
            if current_index >= len(order):
                current_index = 0
            real_index = order[current_index]
            task = tasks[real_index]
            old_progress_id = data.get("progress_msg_id")
            new_progress_id = await send_or_update_progress(
                message.bot,
                message.chat.id,
                user_id,
                short_type,
                task,
                msg_id=old_progress_id,
                edit=True,
                is_revision=False
            )
            new_task_msg_id = await send_or_update_task(
                message.bot,
                message.chat.id,
                state,
                user_id,
                short_type,
                current_index,
                is_revision=False,
                msg_id=None
            )
            await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
        else:
            correction_text = f"Вы исправили: {session_correct}\nОсталось ошибок: {len(errors)}"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Учебный режим", callback_data="grammar_back_to_learning")],
                [InlineKeyboardButton(text="Исправить ошибки", callback_data="grammar_revision_continue")]
            ])
            await message.answer(correction_text, reply_markup=keyboard)

# ----- Показать ответ -----
@router.callback_query(GrammarStates.in_progress, F.data.startswith("grammar_show_answer:"))
@router.callback_query(GrammarStates.waiting_for_text, F.data.startswith("grammar_show_answer:"))
async def show_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Ошибка формата")
        return
    short_type_code, index_str, mode = parts[1], parts[2], parts[3]
    short_type = LONG_TYPE.get(short_type_code)
    if not short_type:
        await callback.answer("Ошибка: неизвестный тип.")
        return
    index = int(index_str)
    is_revision = (mode == "rev")
    user_id = callback.from_user.id

    data = await state.get_data()
    order = data.get("order")
    tasks = get_tasks(short_type)
    if is_revision:
        task_id = data.get("current_task_id")
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            await callback.answer("Задание не найдено")
            return
    else:
        if order is None or index >= len(order):
            await callback.answer("Ошибка порядка")
            return
        real_index = order[index]
        task = tasks[real_index] if real_index < len(tasks) else None
        if not task:
            await callback.answer("Задание не найдено")
            return

    correct_answer = task.get("correct")
    if isinstance(correct_answer, list):
        correct_text = " или ".join(correct_answer)
    else:
        correct_text = str(correct_answer)

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
    level_key = "all"

    if is_revision:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await callback.message.answer("🎉 Вы исправили все ошибки!")
            await state.update_data(is_revision=False)
            order = await get_or_create_order(user_id, short_type)
            await state.update_data(order=order)
            current_index = await get_grammar_index(user_id, type_key, level_key)
            if current_index >= len(order):
                current_index = 0
            real_index = order[current_index]
            task = tasks[real_index]
            old_progress_id = data.get("progress_msg_id")
            new_progress_id = await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                short_type,
                task,
                msg_id=old_progress_id,
                edit=True,
                is_revision=False
            )
            new_task_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                current_index,
                is_revision=False,
                msg_id=None
            )
            await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
        else:
            next_error_id = errors[0]
            old_progress_id = data.get("progress_msg_id")
            new_progress_id = await send_or_update_progress(
                callback.bot,
                callback.message.chat.id,
                user_id,
                short_type,
                task,
                msg_id=old_progress_id,
                edit=True,
                is_revision=True,
                errors_count=len(errors)
            )
            new_task_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                task_id=next_error_id,
                is_revision=True,
                msg_id=None
            )
            await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
    else:
        next_index = index + 1
        if next_index >= len(order):
            next_index = 0
        await set_grammar_index(user_id, type_key, level_key, next_index)
        await state.update_data(current_index=next_index)

        real_next = order[next_index]
        next_task = tasks[real_next]

        old_progress_id = data.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            user_id,
            short_type,
            next_task,
            msg_id=old_progress_id,
            edit=True,
            is_revision=False
        )
        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            user_id,
            short_type,
            next_index,
            is_revision=False,
            msg_id=None
        )
        await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)

    await callback.answer()

# ----- Работа над ошибками -----
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_revision")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_revision")
async def grammar_revision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    if not short_type:
        await callback.message.answer("Сначала выберите тип задания.")
        return

    type_key = make_type_key(short_type)
    level_key = "all"
    errors = await get_grammar_errors(user_id, type_key, level_key)
    if not errors:
        await callback.message.answer("🎉 Ошибок нет! Отличная работа.")
        return

    await state.update_data(is_revision=True, session_correct=0, session_wrong=0)
    task_id = errors[0]
    tasks = get_tasks(short_type)
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        await callback.message.answer("Задание с ошибкой не найдено.")
        return

    old_progress_id = data.get("progress_msg_id")
    new_progress_id = await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        task,
        msg_id=old_progress_id,
        edit=True,
        is_revision=True,
        errors_count=len(errors)
    )
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        task_id=task_id,
        is_revision=True,
        msg_id=None
    )
    await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)

# ----- Обработчик кнопок "Учебный режим" и "Исправить ошибки" -----
@router.callback_query(F.data == "grammar_back_to_learning")
async def back_to_learning(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    short_type = data.get("short_type")
    user_id = callback.from_user.id
    tasks = get_tasks(short_type)
    type_key = make_type_key(short_type)
    level_key = "all"
    order = await get_or_create_order(user_id, short_type)
    await state.update_data(order=order)
    current_index = await get_grammar_index(user_id, type_key, level_key)
    if current_index >= len(order):
        current_index = 0
    await state.update_data(is_revision=False)
    real_index = order[current_index]
    task = tasks[real_index]
    old_progress_id = data.get("progress_msg_id")
    new_progress_id = await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        callback.from_user.id,
        short_type,
        task,
        msg_id=old_progress_id,
        edit=True,
        is_revision=False
    )
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        callback.from_user.id,
        short_type,
        current_index,
        is_revision=False,
        msg_id=None
    )
    await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)

@router.callback_query(F.data == "grammar_revision_continue")
async def revision_continue(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    type_key = make_type_key(short_type)
    level_key = "all"
    errors = await get_grammar_errors(user_id, type_key, level_key)
    if not errors:
        await callback.message.answer("🎉 Ошибок больше нет!")
        return
    await state.update_data(is_revision=True, session_correct=0, session_wrong=0)
    task_id = errors[0]
    tasks = get_tasks(short_type)
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        await callback.message.answer("Задание с ошибкой не найдено.")
        return
    old_progress_id = data.get("progress_msg_id")
    new_progress_id = await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        task,
        msg_id=old_progress_id,
        edit=True,
        is_revision=True,
        errors_count=len(errors)
    )
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        task_id=task_id,
        is_revision=True,
        msg_id=None
    )
    await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)

# ----- Сброс прогресса -----
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_reset")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_reset")
async def grammar_reset_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    confirm_text = (
        "Вы уверены, что хотите сбросить весь прогресс для текущего типа?\n"
        "Статистика, ошибки и текущее задание будут обнулены.\n"
        "Также будет сгенерирован новый порядок заданий.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(confirm_text, reply_markup=get_reset_confirmation_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "grammar_confirm_reset")
async def grammar_confirm_reset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    if not short_type:
        await callback.message.answer("Ошибка: не выбран тип.")
        return

    type_key = make_type_key(short_type)
    level_key = "all"
    await reset_grammar_progress(user_id, type_key, level_key)
    new_order = await reset_order(user_id, short_type)
    await set_grammar_index(user_id, type_key, level_key, 0)

    await state.update_data(
        order=new_order,
        current_index=0,
        is_revision=False,
        session_correct=0,
        session_wrong=0
    )

    tasks = get_tasks(short_type)
    if not tasks:
        await callback.message.answer("Заданий для этого типа нет.")
        return

    # Убираем кнопки у старого задания
    old_task_msg_id = data.get("task_msg_id")
    if old_task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=old_task_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    await callback.message.edit_text("Прогресс сброшен. Задания даны с начала в новом порядке.", reply_markup=None)

    old_progress_id = data.get("progress_msg_id")
    real_index = new_order[0]
    task = tasks[real_index]
    # Редактируем прогресс-сообщение (НЕ УДАЛЯЕМ)
    new_progress_id = await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        task,
        msg_id=old_progress_id,
        edit=True,
        is_revision=False
    )
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        0,
        is_revision=False,
        msg_id=None
    )
    await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)

@router.callback_query(F.data == "grammar_cancel_reset")
async def grammar_cancel_reset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    short_type = data.get("short_type")
    if short_type:
        tasks = get_tasks(short_type)
        order = data.get("order")
        if order is None:
            user_id = callback.from_user.id
            order = await get_or_create_order(user_id, short_type)
            await state.update_data(order=order)
        index = data.get("current_index", 0)
        if index >= len(order):
            index = 0
        real_index = order[index]
        task = tasks[real_index]
        old_progress_id = data.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            callback.from_user.id,
            short_type,
            task,
            msg_id=old_progress_id,
            edit=True,
            is_revision=data.get("is_revision", False)
        )
        task_msg_id = data.get("task_msg_id")
        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            callback.from_user.id,
            short_type,
            index,
            is_revision=data.get("is_revision", False),
            msg_id=task_msg_id
        )
        await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
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
    if not short_type:
        await callback.message.answer("Ошибка: не выбран тип.")
        return

    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)

    if session_correct == 0 and session_wrong == 0:
        text = "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
    else:
        text = "Сессия завершена! 🙌🏻\n"
        text += f"✔️ Правильно: {session_correct}\n"
        text += f"✖️ Ошибок: {session_wrong}"

    # Убираем кнопки у задания
    task_msg_id = data.get("task_msg_id")
    if task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=task_msg_id, reply_markup=None)
        except Exception:
            pass

    # Убираем кнопки у прогресс-сообщения (НО НЕ УДАЛЯЕМ)
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=progress_msg_id, reply_markup=None)
        except Exception:
            pass

    await callback.message.answer(text)

    from handlers.main import show_main_menu
    await show_main_menu(callback.message, edit=False)

    await state.clear()
    await callback.answer()

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
    if not short_type:
        await callback.message.answer("Ошибка: не выбран тип.")
        return
    type_key = make_type_key(short_type)
    level_key = "all"
    await clear_grammar_errors(user_id, type_key, level_key)

    await callback.message.edit_text("Список ошибок очищен. Продолжайте тренировку.")
    await state.update_data(is_revision=False)

    tasks = get_tasks(short_type)
    order = data.get("order")
    if order is None:
        order = await get_or_create_order(user_id, short_type)
        await state.update_data(order=order)
    index = await get_grammar_index(user_id, type_key, level_key)
    if index >= len(order):
        index = 0

    real_index = order[index]
    task = tasks[real_index]
    old_progress_id = data.get("progress_msg_id")
    new_progress_id = await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        task,
        msg_id=old_progress_id,
        edit=True,
        is_revision=False
    )
    new_task_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        index,
        is_revision=False,
        msg_id=None
    )
    await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
    await callback.answer()

@router.callback_query(F.data == "grammar_cancel_clear_errors")
async def grammar_cancel_clear_errors(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    short_type = data.get("short_type")
    if short_type:
        tasks = get_tasks(short_type)
        order = data.get("order")
        if order is None:
            user_id = callback.from_user.id
            order = await get_or_create_order(user_id, short_type)
            await state.update_data(order=order)
        index = data.get("current_index", 0)
        if index >= len(order):
            index = 0
        real_index = order[index]
        task = tasks[real_index]
        old_progress_id = data.get("progress_msg_id")
        new_progress_id = await send_or_update_progress(
            callback.bot,
            callback.message.chat.id,
            callback.from_user.id,
            short_type,
            task,
            msg_id=old_progress_id,
            edit=True,
            is_revision=data.get("is_revision", False)
        )
        task_msg_id = data.get("task_msg_id")
        new_task_msg_id = await send_or_update_task(
            callback.bot,
            callback.message.chat.id,
            state,
            callback.from_user.id,
            short_type,
            index,
            is_revision=data.get("is_revision", False),
            msg_id=task_msg_id
        )
        await state.update_data(progress_msg_id=new_progress_id, task_msg_id=new_task_msg_id)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)