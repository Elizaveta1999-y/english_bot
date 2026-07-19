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

# ... (все константы и функции до обработчиков без изменений) ...

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

    # Используем index как идентификатор задания для ошибок
    task_identifier = index  # <-- ВАЖНО: индекс задания, а не id

    if is_revision:
        if correct:
            logger.info(f"🗑️ Удаление ошибки: user={user_id}, type={type_json}, level={level_json}, index={task_identifier}")
            await remove_reading_error(user_id, type_json, level_json, task_identifier)
            await update_user_stats(user_id, type_json, level_json, True)
            new_correct = data.get("revision_correct", 0) + 1
            await state.update_data(revision_correct=new_correct)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data(session_correct=session_correct)
            # Обновляем индекс для случайного типа
            if short_type == "random":
                order = await get_random_order(user_id, short_level)
                if order:
                    try:
                        pos = order.index(task_identifier)
                        next_index = (pos + 1) % len(order)
                        await set_user_progress(user_id, "random", short_level, next_index)
                        await state.update_data(index=next_index, paragraph_idx=0)
                    except ValueError:
                        pass
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
            await add_reading_error(user_id, type_json, level_json, task_identifier)  # <-- сохраняем индекс
            session_wrong = data.get("session_wrong", 0) + 1
            await state.update_data(session_wrong=session_wrong)
            logger.info(f"❌ Wrong: user={user_id}, type={type_json}, level={level_json} -> добавлена ошибка (index={task_identifier})")

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

    # Обновление индекса для обычного режима (не revision)
    if not is_revision:
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

    task_identifier = index  # <-- ВАЖНО: индекс задания

    if is_revision:
        if correct:
            await remove_reading_error(user_id, type_json, level_json, task_identifier)
            await update_user_stats(user_id, type_json, level_json, True)
            new_correct = data.get("revision_correct", 0) + 1
            await state.update_data(revision_correct=new_correct)
            session_correct = data.get("session_correct", 0) + 1
            await state.update_data(session_correct=session_correct)
            if short_type == "random":
                order = await get_random_order(user_id, short_level)
                if order:
                    try:
                        pos = order.index(task_identifier)
                        next_index = (pos + 1) % len(order)
                        await set_user_progress(user_id, "random", short_level, next_index)
                        await state.update_data(index=next_index, paragraph_idx=0)
                    except ValueError:
                        pass
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
        if short_type == "order" or actual_type == "order":
            explanation = task.get("explanation", "")
            if explanation:
                result_text = f"Неправильно. Правильный ответ: {correct_text}\n\n{explanation}"
            else:
                result_text = f"Неправильно. Правильный ответ: {correct_text}"
        else:
            result_text = f"Неправильно. Правильный ответ: {correct_text}"
    await message.answer(result_text)

    await state.set_state(ReadingStates.in_progress)

    if not is_revision:
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