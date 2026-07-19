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

# ... (все константы и функции до get_all_tasks_for_random без изменений) ...

async def get_all_tasks_for_random(level: str):
    """Возвращает полный список заданий для уровня (без перемешивания)."""
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
    """Возвращает список ID заданий в перемешанном порядке (сохраняет в Redis)."""
    r = await get_redis()
    key = f"random_order:{user_id}:{level}"
    order_data = await r.get(key)
    if order_data:
        return json.loads(order_data)
    # Если нет – генерируем
    all_items = await get_all_tasks_for_random(level)
    if not all_items:
        return []
    random.shuffle(all_items)
    order_ids = [item["task"]["id"] for item in all_items]
    await r.set(key, json.dumps(order_ids))
    return order_ids

async def get_task_by_id(user_id: int, level: str, task_id: int):
    """Возвращает задание и его тип по ID."""
    all_items = await get_all_tasks_for_random(level)
    for item in all_items:
        if item["task"]["id"] == task_id:
            return item["task"], item["type_key"]
    return None, None

# ---------- Функция render_task_message изменена для случайного типа ----------
async def render_task_message(message: Message, state: FSMContext, user_id: int, short_type: str, short_level: str, index: int, paragraph_idx: int = 0, is_revision: bool = False):
    await clear_task_keyboard(message, state)

    if short_type == "random":
        order = await get_random_order(user_id, short_level)
        if not order:
            await message.answer("Нет заданий для этого уровня.")
            return None, None
        if index >= len(order):
            index = 0
        task_id = order[index]
        task, actual_type_key = await get_task_by_id(user_id, short_level, task_id)
        if not task:
            await message.answer("Задание не найдено.")
            return None, None
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

    # ... дальше формирование текста и клавиатуры как раньше ...
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

    if actual_type == "order":
        keyboard = get_action_keyboard(short_type, short_level, index, is_revision)
    elif task.get("input_type") == "text":
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
    return text, keyboard

# ---------- Изменённый choose_level для случайного типа ----------
@router.callback_query(F.data.startswith("reading_level:"))
async def choose_level(callback: CallbackQuery, state: FSMContext):
    _, short_type, short_level = callback.data.split(":")
    user_id = callback.from_user.id

    user_state = get_user_state(user_id)
    user_state["mode"] = None
    set_user_state(user_id, user_state)

    if short_type == "random":
        # Проверяем, есть ли задания
        all_items = await get_all_tasks_for_random(short_level)
        if not all_items:
            await callback.message.edit_text("Задания для этого уровня пока отсутствуют. Попробуйте другой уровень.")
            await callback.answer()
            return
        # Генерируем порядок, если ещё нет
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

    await send_progress_message_edit(callback.message, user_id, short_type, short_level, state)
    await render_task_message(callback.message, state, user_id, short_type, short_level, index, paragraph_idx=0, is_revision=False)
    await state.set_state(ReadingStates.waiting_for_text)
    await callback.answer()

# ---------- В handle_button_answer для случайного типа обновляем индекс ----------
# (нужно заменить блок, где определяется next_index)
# Я покажу изменённый фрагмент:

# В handle_button_answer после обработки ответа, перед переходом к следующему заданию:
    if short_type == "random":
        order = await get_random_order(user_id, short_level)
        if order:
            next_index = index + 1
            if next_index >= len(order):
                next_index = 0
            await set_user_progress(user_id, "random", short_level, next_index)
            await state.update_data(index=next_index, paragraph_idx=0)
            logger.info(f"🔄 Случайный тип: новый индекс {next_index} из {len(order)}")
        else:
            # если нет заданий
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

# Затем переход к следующему заданию (render_task_message)

# Аналогично в handle_text_answer заменить блок с обновлением индекса.

# В show_revision_task для случайного типа используем order:
    if short_type == "random":
        order = await get_random_order(user_id, short_level)
        if order:
            task_id = order[0]  # берём первый из списка ошибок
            task, actual_type = await get_task_by_id(user_id, short_level, task_id)
            if not task:
                await message.answer("Не удалось найти задание для исправления.")
                return
            await state.update_data(actual_type=actual_type, actual_task=task)
            await render_task_message(message, state, user_id, actual_type, short_level, task_id, paragraph_idx=0, is_revision=True)
            await state.update_data(index=task_id, paragraph_idx=0, is_revision=True, error_list=error_ids, error_index=0)

# В confirm_reset добавить удаление ключа random_order при сбросе для случайного типа:
    r = await get_redis()
    await r.delete(f"random_order:{user_id}:{short_level}")