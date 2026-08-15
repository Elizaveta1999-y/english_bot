import logging
import json
import re
import random
from typing import List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import or_f, StateFilter

from data.users import get_user_state, set_user_state
from utils.db import (
    get_grammar_index, set_grammar_index, reset_grammar_index,
    get_grammar_stats, update_grammar_stats, reset_grammar_stats,
    add_grammar_error, remove_grammar_error, get_grammar_errors, clear_grammar_errors,
    reset_grammar_progress,
    get_random_order, set_random_order
)

logger = logging.getLogger(__name__)
router = Router()

# ---------- Состояния ----------
class GrammarStates(StatesGroup):
    choosing_type = State()
    waiting_for_text = State()
    in_progress = State()

# ---------- Глобальный перехват команд (только если активна грамматика) ----------
@router.message(F.text.startswith('/'), StateFilter(GrammarStates.choosing_type, GrammarStates.waiting_for_text, GrammarStates.in_progress))
async def handle_commands_in_grammar(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"[CMD] Получена команда: {message.text} от {message.from_user.id} в активной грамматике")
    data = await state.get_data()
    task_msg_id = data.get("task_msg_id")
    progress_msg_id = data.get("progress_msg_id")
    revision_msg_id = data.get("revision_msg_id")
    logger.info(f"[CMD] task_msg_id={task_msg_id}, progress_msg_id={progress_msg_id}, revision_msg_id={revision_msg_id}")

    # Убираем кнопки у ВСЕХ сообщений
    for msg_id in [task_msg_id, progress_msg_id, revision_msg_id]:
        if msg_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    reply_markup=None
                )
                logger.info(f"[CMD] Кнопки убраны у сообщения {msg_id}")
            except Exception as e:
                logger.error(f"[CMD] Не удалось убрать кнопки у {msg_id}: {e}")
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                    logger.info(f"[CMD] Сообщение {msg_id} удалено (не удалось убрать кнопки)")
                except Exception as e2:
                    logger.error(f"[CMD] Не удалось удалить сообщение {msg_id}: {e2}")

    try:
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        logger.info("[CMD] Отправлено 'Практика завершена' с удалением клавиатуры")
    except Exception as e:
        logger.error(f"[CMD] Ошибка отправки 'Практика завершена': {e}")

    from handlers.main import show_main_menu
    try:
        await show_main_menu(message, edit=False)
        logger.info("[CMD] Главное меню показано (новое сообщение)")
    except Exception as e:
        logger.error(f"[CMD] Ошибка показа главного меню: {e}")

    await state.clear()
    user_state = get_user_state(message.from_user.id)
    user_state["mode"] = ""
    set_user_state(message.from_user.id, user_state)
    logger.info("[CMD] Состояние и режим сброшены")

# ---------- Обработчик не-текстовых сообщений ----------
@router.message(
    or_f(
        GrammarStates.in_progress,
        GrammarStates.waiting_for_text
    ),
    ~F.text
)
async def handle_non_text_in_grammar(message: Message, state: FSMContext):
    logger.info(f"[NON-TEXT] Получено не-текстовое сообщение от {message.from_user.id}")
    await message.answer("Введите текстовый ответ")

# ---------- Загрузка заданий ----------
TASKS_FILE = "data/grammar_tasks.json"

def load_tasks() -> Dict[str, List[Dict]]:
    logger.info("[LOAD] Загрузка заданий из файла")
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"[LOAD] Загружено {len(data)} типов заданий")
    return data

RAW_TASKS = load_tasks()
TASKS_BY_TYPE = {}
for task_type, tasks in RAW_TASKS.items():
    TASKS_BY_TYPE[task_type] = tasks
    logger.info(f"[LOAD] Тип '{task_type}': {len(tasks)} заданий")

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

# ---------- Клавиатуры ----------
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="grammar_revision")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="grammar_reset")]
    ])

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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить", callback_data="grammar_confirm_reset")],
        [InlineKeyboardButton(text="Назад", callback_data="grammar_cancel_reset")]
    ])

def get_clear_errors_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить ошибки", callback_data="grammar_confirm_clear_errors")],
        [InlineKeyboardButton(text="Назад", callback_data="grammar_cancel_clear_errors")]
    ])

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
    logger.info(f"[ORDER] Получение порядка для {user_id}, тип {short_type}")
    order = await get_random_order(user_id, type_key)
    if order is None:
        tasks = get_tasks(short_type)
        indices = list(range(len(tasks)))
        random.shuffle(indices)
        await set_random_order(user_id, type_key, indices)
        logger.info(f"[ORDER] Создан новый порядок для {user_id}, тип {short_type}")
        return indices
    else:
        if isinstance(order, str):
            try:
                order = json.loads(order)
            except:
                order = []
        logger.info(f"[ORDER] Порядок получен из БД, длина {len(order)}")
        return order

async def reset_order(user_id: int, short_type: str) -> List[int]:
    type_key = make_type_key(short_type)
    tasks = get_tasks(short_type)
    indices = list(range(len(tasks)))
    random.shuffle(indices)
    await set_random_order(user_id, type_key, indices)
    logger.info(f"[ORDER] Порядок сброшен для {user_id}, тип {short_type}")
    return indices

# ---------- Отправка прогресса ----------
async def send_or_update_progress(
    bot: Bot,
    chat_id: int,
    user_id: int,
    short_type: str,
    task: Dict,
    msg_id: int = None,
    edit: bool = False
) -> int:
    logger.info(f"[PROGRESS] user={user_id}, type={short_type}, edit={edit}, msg_id={msg_id}")
    if edit and msg_id is None:
        logger.warning("[PROGRESS] edit=True без msg_id – игнорируем")
        return None

    type_key = make_type_key(short_type)
    correct, wrong = await get_grammar_stats(user_id, type_key, "all")
    errors = await get_grammar_errors(user_id, type_key, "all")
    errors_len = len(errors)
    logger.info(f"[PROGRESS] stats: correct={correct}, wrong={wrong}, errors={errors_len}")

    display_type = f"{TYPE_EMOJIS.get(short_type, '')} {short_type.replace('_', ' ')}"

    if short_type == "раскрытие_скобок":
        instruction = "Раскройте скобки, впишите ответ (1–2 слова)."
    elif short_type == "вставка_пропусков":
        instruction = "Вставьте необходимое слово (артикль, предлог, союз, глагол и тд.)"
    elif short_type == "отрицание":
        instruction = "Перепишите предложение в отрицательную форму"
    elif short_type in ("to_be_выбор", "to_be_скобки"):
        instruction = "Вставьте правильную форму глагола to be"
    else:
        instruction, _ = extract_instruction_and_task(task['question'])

    text = f"<b>Режим:</b> {display_type}\n\n"
    text += f"{instruction}\n\n"
    text += f"<b>Ваш прогресс:</b>\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {errors_len}"
    keyboard = get_progress_keyboard()

    if not edit and msg_id is None:
        sent = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
        logger.info(f"[PROGRESS] Создано новое сообщение, id={sent.message_id}")
        return sent.message_id

    if edit and msg_id is not None:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard, parse_mode="HTML")
            logger.info(f"[PROGRESS] Отредактировано сообщение {msg_id}")
            return msg_id
        except Exception as e:
            logger.error(f"[PROGRESS] Ошибка редактирования {msg_id}: {e}")
            try:
                await bot.delete_message(chat_id, msg_id)
                logger.info(f"[PROGRESS] Старое сообщение {msg_id} удалено")
            except Exception as e2:
                logger.error(f"[PROGRESS] Не удалось удалить сообщение {msg_id}: {e2}")
            sent = await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
            logger.info(f"[PROGRESS] Отправлено новое вместо редактирования, id={sent.message_id}")
            return sent.message_id

    logger.warning(f"[PROGRESS] Непонятная ситуация, msg_id={msg_id}, edit={edit}")
    return msg_id

# ---------- Отправка задания (ИСПРАВЛЕНО) ----------
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
    """
    Отправляет или редактирует задание.
    - В обычном режиме всегда создаёт новое сообщение (msg_id игнорируется для редактирования).
    - В режиме revision тоже всегда создаёт новое сообщение.
    Если msg_id передан, он используется только для того, чтобы убрать кнопки у старого сообщения.
    """
    logger.info(f"[TASK] user={user_id}, type={short_type}, revision={is_revision}, msg_id={msg_id}")
    tasks = get_tasks(short_type)
    if task_id is not None:
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            logger.error(f"[TASK] Задание с id {task_id} не найдено")
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
            logger.error(f"[TASK] Задание по индексу {index} не найдено")
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
    logger.info(f"[TASK] task_text: '{task_text[:50]}...'")

    if short_type == "to_be_скобки":
        hint = "(was/were)"
        logger.info(f"[TASK] to_be_скобки, добавляем hint: {hint}")
        if not task_text or len(task_text.split()) <= 2:
            task_text = task.get('question', '')
        task_text = f"{hint}\n{task_text}"
    elif short_type == "to_be_выбор":
        hint = "(am/is/are)"
        logger.info(f"[TASK] to_be_выбор, добавляем hint: {hint}")
        if not task_text or len(task_text.split()) <= 2:
            task_text = task.get('question', '')
        task_text = f"{hint}\n{task_text}"

    short_type_code = SHORT_TYPE[short_type]
    callback_index = index if not is_revision else -1
    keyboard = get_task_keyboard(short_type_code, callback_index, is_revision)

    # Если был передан старый msg_id, убираем у него кнопки (если это не revision – мы уже сделали это отдельно, но на всякий случай)
    if msg_id:
        try:
            await bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
            logger.info(f"[TASK] Убраны кнопки у старого сообщения {msg_id}")
        except Exception as e:
            logger.error(f"[TASK] Не удалось убрать кнопки у {msg_id}: {e}")

    # Всегда отправляем новое сообщение
    sent = await bot.send_message(chat_id, task_text, reply_markup=keyboard, parse_mode="HTML")
    logger.info(f"[TASK] Создано новое задание, id={sent.message_id}")
    if task.get("input_type") == "text":
        await state.set_state(GrammarStates.waiting_for_text)
    else:
        await state.set_state(GrammarStates.in_progress)
    return sent.message_id

# ---------- Вход в режим выбора типа ----------
async def enter_grammar_mode(message: Message, user_id: int, edit: bool = False, state: FSMContext = None):
    logger.info(f"[ENTER] user={user_id}, edit={edit}")
    if state:
        await state.set_state(GrammarStates.choosing_type)
    text = "🔀 Грамматика\n\nВыберите тип задания:"
    keyboard = get_type_keyboard()
    if edit:
        try:
            await message.edit_text(text, reply_markup=keyboard)
            logger.info("[ENTER] Сообщение отредактировано")
        except Exception as e:
            logger.error(f"[ENTER] Не удалось отредактировать: {e}, отправляем новое")
            await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)
        logger.info("[ENTER] Отправлено новое сообщение")

# ---------- Обработчики callback'ов ----------
@router.callback_query(F.data == "start_grammar")
async def start_grammar(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] start_grammar от {callback.from_user.id}")
    await callback.answer()
    data = await state.get_data()
    logger.info(f"[start_grammar] data: {data}")
    for key in ["task_msg_id", "progress_msg_id", "revision_msg_id"]:
        msg_id = data.get(key)
        if msg_id:
            try:
                await callback.bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=msg_id,
                    reply_markup=None
                )
                logger.info(f"[start_grammar] Кнопки убраны у сообщения {msg_id}")
            except Exception as e:
                logger.error(f"[start_grammar] Ошибка убирания кнопок у {msg_id}: {e}")
                try:
                    await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=msg_id)
                    logger.info(f"[start_grammar] Сообщение {msg_id} удалено")
                except Exception as e2:
                    logger.error(f"[start_grammar] Не удалось удалить сообщение {msg_id}: {e2}")
        else:
            logger.warning(f"[start_grammar] {key} отсутствует в состоянии")

    await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)

@router.callback_query(F.data == "grammar_back_to_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] back_to_main_menu от {callback.from_user.id}")
    await callback.answer()
    try:
        await callback.message.delete()
        logger.info("[back_to_main_menu] Сообщение с кнопками удалено")
    except Exception as e:
        logger.error(f"[back_to_main_menu] Не удалось удалить сообщение: {e}")
    await state.clear()
    from handlers.main import show_main_menu
    try:
        await show_main_menu(callback.message, edit=False)
        logger.info("[back_to_main_menu] Главное меню отправлено")
    except Exception as e:
        logger.error(f"[back_to_main_menu] Ошибка показа главного меню: {e}")

@router.callback_query(GrammarStates.choosing_type, F.data == "grammar_back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] back_to_types от {callback.from_user.id}")
    await callback.answer()
    try:
        await callback.message.delete()
        logger.info("[back_to_types] Сообщение с кнопками удалено")
    except Exception as e:
        logger.error(f"[back_to_types] Не удалось удалить сообщение: {e}")
    await state.clear()
    from handlers.main import show_main_menu
    try:
        await show_main_menu(callback.message, edit=False)
        logger.info("[back_to_types] Главное меню отправлено")
    except Exception as e:
        logger.error(f"[back_to_types] Ошибка показа главного меню: {e}")

@router.callback_query(GrammarStates.choosing_type, F.data.startswith("grammar_type_"))
async def select_type(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] select_type от {callback.from_user.id}, data={callback.data}")
    await callback.answer()
    short_code = callback.data.replace("grammar_type_", "")
    short_type = LONG_TYPE.get(short_code)
    if not short_type:
        logger.error(f"[select_type] Неизвестный тип: {short_code}")
        await callback.message.answer("Ошибка: неизвестный тип.")
        return

    user_id = callback.from_user.id
    tasks = get_tasks(short_type)
    if not tasks:
        logger.warning(f"[select_type] Нет заданий для типа {short_type}")
        await callback.message.answer("Заданий для этого типа пока нет.")
        return

    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)

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
        task_msg_id=None,
        revision_msg_id=None
    )

    bot = callback.bot
    chat_id = callback.message.chat.id
    real_index = order[index]
    task = tasks[real_index]

    progress_msg_id = await send_or_update_progress(
        bot, chat_id, user_id, short_type, task, msg_id=None, edit=False
    )
    task_msg_id = await send_or_update_task(
        bot, chat_id, state, user_id, short_type, index, is_revision=False, msg_id=None
    )

    await state.update_data(progress_msg_id=progress_msg_id, task_msg_id=task_msg_id)
    try:
        await callback.message.delete()
        logger.info("[select_type] Сообщение с выбором типа удалено")
    except Exception as e:
        logger.error(f"[select_type] Не удалось удалить сообщение с выбором типа: {e}")
    logger.info(f"[select_type] Сессия начата, progress_id={progress_msg_id}, task_id={task_msg_id}")

# ---------- Обработка ответов (кнопки) ----------
@router.callback_query(GrammarStates.in_progress, F.data.startswith("grammar_answer:"))
@router.callback_query(GrammarStates.waiting_for_text, F.data.startswith("grammar_answer:"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] handle_button_answer от {callback.from_user.id}, data={callback.data}")
    parts = callback.data.split(":")
    if len(parts) < 5:
        logger.error("[handle_button_answer] Неверный формат callback")
        await callback.answer("Ошибка формата")
        return
    short_type_code, index_str, chosen_idx_str, mode = parts[1], parts[2], parts[3], parts[4]
    short_type = LONG_TYPE.get(short_type_code)
    if not short_type:
        logger.error(f"[handle_button_answer] Неизвестный тип: {short_type_code}")
        await callback.answer("Ошибка: неизвестный тип.")
        return
    index = int(index_str)
    chosen_idx = int(chosen_idx_str)
    is_revision = (mode == "rev")
    user_id = callback.from_user.id

    data = await state.get_data()
    order = data.get("order")
    if order is None or index >= len(order):
        logger.error(f"[handle_button_answer] Ошибка порядка, order={order}, index={index}")
        await callback.answer("Ошибка порядка заданий")
        return
    real_index = order[index]
    tasks = get_tasks(short_type)
    if real_index >= len(tasks):
        logger.error(f"[handle_button_answer] Индекс {real_index} вне диапазона")
        await callback.answer("Задание не найдено")
        return
    task = tasks[real_index]
    correct = (chosen_idx == task.get("correct", -1))

    type_key = make_type_key(short_type)
    level_key = "all"
    session_correct = data.get("session_correct", 0)
    session_wrong = data.get("session_wrong", 0)

    logger.info(f"[handle_button_answer] Ответ {'правильный' if correct else 'неправильный'}")

    if is_revision:
        if correct:
            await remove_grammar_error(user_id, type_key, level_key, task["id"])
            await update_grammar_stats(user_id, type_key, level_key, True)
            session_correct += 1
            await state.update_data(session_correct=session_correct)
            logger.info("[handle_button_answer] Ошибка удалена, статистика обновлена")
        else:
            session_wrong += 1
            await state.update_data(session_wrong=session_wrong)
            logger.info("[handle_button_answer] Ошибка не исправлена, session_wrong++")
    else:
        if correct:
            await update_grammar_stats(user_id, type_key, level_key, True)
            session_correct += 1
            await state.update_data(session_correct=session_correct)
            await remove_grammar_error(user_id, type_key, level_key, task["id"])
            logger.info("[handle_button_answer] Правильно, статистика обновлена")
        else:
            await update_grammar_stats(user_id, type_key, level_key, False)
            session_wrong += 1
            await state.update_data(session_wrong=session_wrong)
            await add_grammar_error(user_id, type_key, level_key, task["id"])
            logger.info("[handle_button_answer] Неправильно, добавлена ошибка")

    # Убираем кнопки у текущего задания (старого)
    old_task_msg_id = data.get("task_msg_id") if not is_revision else data.get("revision_msg_id")
    if old_task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=old_task_msg_id,
                reply_markup=None
            )
            logger.info(f"[handle_button_answer] Кнопки убраны у задания {old_task_msg_id}")
        except Exception as e:
            logger.error(f"[handle_button_answer] Ошибка убирания кнопок у задания: {e}")

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
    logger.info(f"[handle_button_answer] Отправлен результат: {result_text}")

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
            edit=True
        )
        # Создаём НОВОЕ задание (msg_id=None)
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
        logger.info(f"[handle_button_answer] Переход к следующему заданию, index={next_index}")
    else:
        # Режим revision
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            # Все ошибки исправлены
            await callback.message.answer("🎉 Вы исправили все ошибки!")
            logger.info("[handle_button_answer] Все ошибки исправлены")
            await state.update_data(is_revision=False)
            # Удаляем revision-сообщение (оно уже без кнопок, но удалим для чистоты)
            rev_msg_id = data.get("revision_msg_id")
            if rev_msg_id:
                try:
                    await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=rev_msg_id)
                    logger.info(f"[handle_button_answer] Revision-сообщение удалено, id={rev_msg_id}")
                except Exception as e:
                    logger.error(f"[handle_button_answer] Ошибка удаления revision-сообщения: {e}")
                await state.update_data(revision_msg_id=None)
            # Возврат в учебный режим (создаём новое задание)
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
                edit=True
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
            logger.info("[handle_button_answer] Возврат в учебный режим")
        else:
            # Есть ещё ошибки – переходим к следующему ошибочному заданию (создаём новое сообщение)
            next_error_id = errors[0]
            # Убираем кнопки у текущего revision-сообщения (если ещё не убрали)
            rev_msg_id = data.get("revision_msg_id")
            if rev_msg_id:
                try:
                    await callback.bot.edit_message_reply_markup(
                        chat_id=callback.message.chat.id,
                        message_id=rev_msg_id,
                        reply_markup=None
                    )
                    logger.info(f"[handle_button_answer] Кнопки убраны у revision-сообщения {rev_msg_id}")
                except Exception as e:
                    logger.error(f"[handle_button_answer] Ошибка убирания кнопок у revision: {e}")
            # Создаём новое revision-задание
            new_rev_msg_id = await send_or_update_task(
                callback.bot,
                callback.message.chat.id,
                state,
                user_id,
                short_type,
                task_id=next_error_id,
                is_revision=True,
                msg_id=None  # всегда новое
            )
            await state.update_data(revision_msg_id=new_rev_msg_id)
            logger.info(f"[handle_button_answer] Показ следующего ошибочного задания, id={next_error_id}")

    await callback.answer()

# ---------- Обработка текстовых ответов ----------
@router.message(GrammarStates.waiting_for_text, F.text)
async def handle_text_answer(message: Message, state: FSMContext):
    logger.info(f"[TEXT] handle_text_answer от {message.from_user.id}, текст: {message.text[:50]}...")
    data = await state.get_data()
    short_type = data.get("short_type")
    index = data.get("current_index", 0)
    is_revision = data.get("is_revision", False)
    task = data.get("actual_task")
    if not task:
        logger.warning("[TEXT] Задание не найдено в состоянии")
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

    logger.info(f"[TEXT] Ответ {'правильный' if correct else 'неправильный'}")

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
    old_task_msg_id = data.get("task_msg_id") if not is_revision else data.get("revision_msg_id")
    if old_task_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=old_task_msg_id,
                reply_markup=None
            )
            logger.info(f"[TEXT] Кнопки убраны у задания {old_task_msg_id}")
        except Exception as e:
            logger.error(f"[TEXT] Ошибка убирания кнопок: {e}")

    if correct:
        result_text = "Правильно!"
    else:
        if isinstance(correct_answer, list):
            correct_text = " или ".join(correct_answer)
        else:
            correct_text = str(correct_answer)
        result_text = f"Неправильно. Правильный ответ: {correct_text}"

    await message.answer(result_text)
    logger.info(f"[TEXT] Отправлен результат: {result_text}")

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
            edit=True
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
        logger.info(f"[TEXT] Переход к следующему заданию, index={next_index}")
    else:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await message.answer("🎉 Вы исправили все ошибки!")
            logger.info("[TEXT] Все ошибки исправлены")
            await state.update_data(is_revision=False)
            rev_msg_id = data.get("revision_msg_id")
            if rev_msg_id:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=rev_msg_id)
                    logger.info(f"[TEXT] Revision-сообщение удалено, id={rev_msg_id}")
                except Exception as e:
                    logger.error(f"[TEXT] Ошибка удаления revision-сообщения: {e}")
                await state.update_data(revision_msg_id=None)
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
                edit=True
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
            logger.info("[TEXT] Возврат в учебный режим")
        else:
            # Есть ещё ошибки – переходим к следующему (создаём новое)
            next_error_id = errors[0]
            rev_msg_id = data.get("revision_msg_id")
            if rev_msg_id:
                try:
                    await message.bot.edit_message_reply_markup(
                        chat_id=message.chat.id,
                        message_id=rev_msg_id,
                        reply_markup=None
                    )
                    logger.info(f"[TEXT] Кнопки убраны у revision-сообщения {rev_msg_id}")
                except Exception as e:
                    logger.error(f"[TEXT] Ошибка убирания кнопок у revision: {e}")
            new_rev_msg_id = await send_or_update_task(
                message.bot,
                message.chat.id,
                state,
                user_id,
                short_type,
                task_id=next_error_id,
                is_revision=True,
                msg_id=None
            )
            await state.update_data(revision_msg_id=new_rev_msg_id)
            logger.info(f"[TEXT] Показ следующего ошибочного задания, id={next_error_id}")

# ---------- Показать ответ (исправлено) ----------
@router.callback_query(GrammarStates.in_progress, F.data.startswith("grammar_show_answer:"))
@router.callback_query(GrammarStates.waiting_for_text, F.data.startswith("grammar_show_answer:"))
async def show_answer(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] show_answer от {callback.from_user.id}, data={callback.data}")
    parts = callback.data.split(":")
    if len(parts) < 4:
        logger.error("[show_answer] Неверный формат callback")
        await callback.answer("Ошибка формата")
        return
    short_type_code, index_str, mode = parts[1], parts[2], parts[3]
    short_type = LONG_TYPE.get(short_type_code)
    if not short_type:
        logger.error(f"[show_answer] Неизвестный тип: {short_type_code}")
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
            logger.error(f"[show_answer] Задание с id {task_id} не найдено")
            await callback.answer("Задание не найдено")
            return
    else:
        if order is None or index >= len(order):
            logger.error(f"[show_answer] Ошибка порядка, order={order}, index={index}")
            await callback.answer("Ошибка порядка")
            return
        real_index = order[index]
        task = tasks[real_index] if real_index < len(tasks) else None
        if not task:
            logger.error(f"[show_answer] Задание по индексу {real_index} не найдено")
            await callback.answer("Задание не найдено")
            return

    correct_answer = task.get("correct")
    if isinstance(correct_answer, list):
        correct_text = " или ".join(correct_answer)
    else:
        correct_text = str(correct_answer)

    # Убираем кнопки у текущего задания
    old_task_msg_id = data.get("task_msg_id") if not is_revision else data.get("revision_msg_id")
    if old_task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=old_task_msg_id,
                reply_markup=None
            )
            logger.info(f"[show_answer] Кнопки убраны у задания {old_task_msg_id}")
        except Exception as e:
            logger.error(f"[show_answer] Ошибка убирания кнопок: {e}")

    await callback.message.answer(f"Правильный ответ: {correct_text}")
    logger.info(f"[show_answer] Отправлен правильный ответ: {correct_text}")

    type_key = make_type_key(short_type)
    level_key = "all"

    if is_revision:
        errors = await get_grammar_errors(user_id, type_key, level_key)
        if not errors:
            await callback.message.answer("🎉 Вы исправили все ошибки!")
            logger.info("[show_answer] Все ошибки исправлены")
            await state.update_data(is_revision=False)
            rev_msg_id = data.get("revision_msg_id")
            if rev_msg_id:
                try:
                    await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=rev_msg_id)
                    logger.info(f"[show_answer] Revision-сообщение удалено, id={rev_msg_id}")
                except Exception as e:
                    logger.error(f"[show_answer] Ошибка удаления revision-сообщения: {e}")
                await state.update_data(revision_msg_id=None)
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
                edit=True
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
            logger.info("[show_answer] Возврат в учебный режим")
        else:
            # Проверяем, является ли текущее задание последним в списке ошибок
            current_task_id = data.get("current_task_id")
            remaining_errors = [e for e in errors if e != current_task_id]
            if not remaining_errors:
                # Это было последнее ошибочное задание – показываем сообщение о просмотре
                await callback.message.answer(
                    "Вы просмотрели все задания с ошибками.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Учебный режим", callback_data="grammar_back_to_learning")]
                    ])
                )
                logger.info("[show_answer] Показано сообщение о просмотре всех ошибок")
            else:
                # Есть ещё ошибки – переходим к следующей (создаём новое)
                next_error_id = remaining_errors[0]
                rev_msg_id = data.get("revision_msg_id")
                # Убираем кнопки у старого revision-сообщения (если ещё не убрали)
                if rev_msg_id:
                    try:
                        await callback.bot.edit_message_reply_markup(
                            chat_id=callback.message.chat.id,
                            message_id=rev_msg_id,
                            reply_markup=None
                        )
                        logger.info(f"[show_answer] Кнопки убраны у revision-сообщения {rev_msg_id}")
                    except Exception as e:
                        logger.error(f"[show_answer] Ошибка убирания кнопок у revision: {e}")
                new_rev_msg_id = await send_or_update_task(
                    callback.bot,
                    callback.message.chat.id,
                    state,
                    user_id,
                    short_type,
                    task_id=next_error_id,
                    is_revision=True,
                    msg_id=None
                )
                await state.update_data(revision_msg_id=new_rev_msg_id)
                logger.info(f"[show_answer] Показ следующего ошибочного задания, id={next_error_id}")
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
            edit=True
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
        logger.info(f"[show_answer] Переход к следующему заданию, index={next_index}")

    await callback.answer()

# ---------- Работа над ошибками ----------
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_revision")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_revision")
async def grammar_revision(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_revision от {callback.from_user.id}")
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    if not short_type:
        logger.warning("[grammar_revision] Тип не выбран")
        await callback.message.answer("Сначала выберите тип задания.")
        return

    type_key = make_type_key(short_type)
    level_key = "all"
    errors = await get_grammar_errors(user_id, type_key, level_key)
    if not errors:
        logger.info("[grammar_revision] Ошибок нет")
        await callback.message.answer("🎉 Ошибок нет! Отличная работа.")
        return

    # Убираем кнопки у прогресса и у текущего задания
    old_progress_id = data.get("progress_msg_id")
    if old_progress_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=old_progress_id,
                reply_markup=None
            )
            logger.info(f"[grammar_revision] Кнопки убраны у прогресса {old_progress_id}")
        except Exception as e:
            logger.error(f"[grammar_revision] Ошибка убирания кнопок у прогресса: {e}")

    old_task_msg_id = data.get("task_msg_id")
    if old_task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=old_task_msg_id,
                reply_markup=None
            )
            logger.info(f"[grammar_revision] Кнопки убраны у старого задания {old_task_msg_id}")
        except Exception as e:
            logger.error(f"[grammar_revision] Ошибка убирания кнопок у старого задания: {e}")

    await state.update_data(is_revision=True, session_correct=0, session_wrong=0)
    task_id = errors[0]
    tasks = get_tasks(short_type)
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        logger.error(f"[grammar_revision] Задание с id {task_id} не найдено")
        await callback.message.answer("Задание с ошибкой не найдено.")
        return

    emoji = TYPE_EMOJIS.get(short_type, "")
    display_type = f"{emoji} {short_type.replace('_', ' ')}".strip()
    header_text = f"<b>Работа над ошибками</b>\nТип: {display_type}\n\nЗаданий на исправление: {len(errors)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Учебный режим", callback_data="grammar_back_to_learning")]
    ])
    await callback.message.answer(header_text, reply_markup=keyboard, parse_mode="HTML")
    logger.info("[grammar_revision] Отправлен заголовок с кнопкой 'Учебный режим'")

    # Отправляем первое задание в revision (новое сообщение)
    rev_msg_id = await send_or_update_task(
        callback.bot,
        callback.message.chat.id,
        state,
        user_id,
        short_type,
        task_id=task_id,
        is_revision=True,
        msg_id=None  # всегда новое
    )
    await state.update_data(revision_msg_id=rev_msg_id)
    logger.info(f"[grammar_revision] Начало работы над ошибками, rev_msg_id={rev_msg_id}")

# ---------- Обработчик кнопки "Учебный режим" ----------
@router.callback_query(F.data == "grammar_back_to_learning")
async def back_to_learning(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] back_to_learning от {callback.from_user.id}")
    await callback.answer()
    data = await state.get_data()
    short_type = data.get("short_type")
    user_id = callback.from_user.id
    if not short_type:
        logger.warning("[back_to_learning] Тип не выбран, переход в главное меню")
        await state.clear()
        from handlers.main import show_main_menu
        await show_main_menu(callback.message, edit=True)
        return

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
        edit=True
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
    rev_msg_id = data.get("revision_msg_id")
    if rev_msg_id:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=rev_msg_id)
            logger.info(f"[back_to_learning] Revision-сообщение удалено, id={rev_msg_id}")
        except Exception as e:
            logger.error(f"[back_to_learning] Ошибка удаления revision-сообщения: {e}")
        await state.update_data(revision_msg_id=None)
    logger.info("[back_to_learning] Возврат в учебный режим")
    await callback.message.delete()

# ---------- Сброс прогресса ----------
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_reset")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_reset")
async def grammar_reset_confirm(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_reset_confirm от {callback.from_user.id}")
    await callback.answer()
    confirm_text = (
        "Вы уверены, что хотите сбросить весь прогресс для текущего типа?\n"
        "Статистика, ошибки и текущее задание будут обнулены.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(confirm_text, reply_markup=get_reset_confirmation_keyboard(), parse_mode="HTML")
    logger.info("[grammar_reset_confirm] Показано подтверждение сброса")

@router.callback_query(F.data == "grammar_confirm_reset")
async def grammar_confirm_reset(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_confirm_reset от {callback.from_user.id}")
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    if not short_type:
        logger.error("[grammar_confirm_reset] Тип не выбран")
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
        logger.warning("[grammar_confirm_reset] Нет заданий для типа")
        await callback.message.answer("Заданий для этого типа нет.")
        return

    old_task_msg_id = data.get("task_msg_id")
    if old_task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=old_task_msg_id,
                reply_markup=None
            )
            logger.info(f"[grammar_confirm_reset] Кнопки убраны у старого задания {old_task_msg_id}")
        except Exception as e:
            logger.error(f"[grammar_confirm_reset] Ошибка убирания кнопок: {e}")

    await callback.message.edit_text("Прогресс сброшен. Задания даны с начала.", reply_markup=None)
    logger.info("[grammar_confirm_reset] Сообщение подтверждения изменено на 'Прогресс сброшен'")

    old_progress_id = data.get("progress_msg_id")
    real_index = new_order[0]
    task = tasks[real_index]
    new_progress_id = await send_or_update_progress(
        callback.bot,
        callback.message.chat.id,
        user_id,
        short_type,
        task,
        msg_id=old_progress_id,
        edit=True
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
    logger.info("[grammar_confirm_reset] Прогресс и задание обновлены после сброса")

@router.callback_query(F.data == "grammar_cancel_reset")
async def grammar_cancel_reset(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_cancel_reset от {callback.from_user.id}")
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
            edit=True
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
            logger.info("[grammar_cancel_reset] Сообщение подтверждения удалено")
        except Exception as e:
            logger.error(f"[grammar_cancel_reset] Ошибка удаления сообщения: {e}")
        logger.info("[grammar_cancel_reset] Возврат к прогрессу и заданию")
    else:
        logger.warning("[grammar_cancel_reset] Тип не выбран, переход в режим выбора типа")
        await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)

# ---------- Завершение сессии ----------
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_finish_session")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_finish_session")
async def grammar_finish_session(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_finish_session от {callback.from_user.id}")
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    if not short_type:
        logger.error("[grammar_finish_session] Тип не выбран")
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

    task_msg_id = data.get("task_msg_id")
    if task_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=task_msg_id, reply_markup=None)
            logger.info(f"[grammar_finish_session] Кнопки убраны у задания {task_msg_id}")
        except Exception as e:
            logger.error(f"[grammar_finish_session] Ошибка убирания кнопок: {e}")
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=progress_msg_id, reply_markup=None)
            logger.info(f"[grammar_finish_session] Кнопки убраны у прогресса {progress_msg_id}")
        except Exception as e:
            logger.error(f"[grammar_finish_session] Ошибка убирания кнопок: {e}")
    rev_msg_id = data.get("revision_msg_id")
    if rev_msg_id:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=rev_msg_id)
            logger.info(f"[grammar_finish_session] Revision-сообщение удалено, id={rev_msg_id}")
        except Exception as e:
            logger.error(f"[grammar_finish_session] Ошибка удаления revision-сообщения: {e}")

    await callback.message.answer(text)
    logger.info(f"[grammar_finish_session] Отправлен текст завершения: {text}")

    from handlers.main import show_main_menu
    try:
        await show_main_menu(callback.message, edit=False)
        logger.info("[grammar_finish_session] Главное меню показано")
    except Exception as e:
        logger.error(f"[grammar_finish_session] Ошибка показа главного меню: {e}")

    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    logger.info("[grammar_finish_session] Состояние и режим сброшены")
    await callback.answer()

# ---------- Сброс ошибок ----------
@router.callback_query(GrammarStates.in_progress, F.data == "grammar_clear_errors")
@router.callback_query(GrammarStates.waiting_for_text, F.data == "grammar_clear_errors")
async def grammar_clear_errors_confirm(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_clear_errors_confirm от {callback.from_user.id}")
    await callback.answer()
    confirm_text = (
        "Вы уверены, что хотите сбросить все ошибки?\n"
        "Все задания с ошибками будут удалены. Вы сможете начать их заново.\n\n"
        "Это действие нельзя отменить."
    )
    await callback.message.edit_text(confirm_text, reply_markup=get_clear_errors_confirmation_keyboard(), parse_mode="HTML")
    logger.info("[grammar_clear_errors_confirm] Показано подтверждение очистки ошибок")

@router.callback_query(F.data == "grammar_confirm_clear_errors")
async def grammar_confirm_clear_errors(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_confirm_clear_errors от {callback.from_user.id}")
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    short_type = data.get("short_type")
    if not short_type:
        logger.error("[grammar_confirm_clear_errors] Тип не выбран")
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
        edit=True
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
    logger.info("[grammar_confirm_clear_errors] Ошибки очищены, прогресс и задание обновлены")
    await callback.answer()

@router.callback_query(F.data == "grammar_cancel_clear_errors")
async def grammar_cancel_clear_errors(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[CALLBACK] grammar_cancel_clear_errors от {callback.from_user.id}")
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
            edit=True
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
            logger.info("[grammar_cancel_clear_errors] Сообщение подтверждения удалено")
        except Exception as e:
            logger.error(f"[grammar_cancel_clear_errors] Ошибка удаления сообщения: {e}")
        logger.info("[grammar_cancel_clear_errors] Возврат к прогрессу и заданию")
    else:
        await enter_grammar_mode(callback.message, callback.from_user.id, edit=True, state=state)