import json
import os
import tempfile
import re
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Voice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.deepseek_govorenie import check_govorenie
from services.speech_recognition import speech_to_text
from utils.db import (
    get_govorenie_task_id, set_govorenie_task_id,
    get_govorenie_stats, update_govorenie_stats,
    reset_govorenie_progress, init_govorenie_session
)
# Убрали глобальный импорт show_main_menu

logger = logging.getLogger(__name__)
router = Router()

TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/govorenie_tasks.json")

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

ALL_TASKS = load_tasks()

class GovorenieStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_voice = State()
    showing_progress = State()
    confirm_reset = State()

def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Чтение вслух", callback_data="g_type_reading")],
        [InlineKeyboardButton(text="⏱ Беглость", callback_data="g_type_fluency")],
        [InlineKeyboardButton(text="🎤 Интервью", callback_data="g_type_interview")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_levels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Новичок", callback_data="g_level_beginner")],
        [InlineKeyboardButton(text="📚 Любитель", callback_data="g_level_intermediate")],
        [InlineKeyboardButton(text="🎓 Эксперт", callback_data="g_level_advanced")],
        [InlineKeyboardButton(text="🔙 Назад к типам", callback_data="back_to_types")]
    ])

def get_action_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Следующее задание", callback_data="g_next_task"),
            InlineKeyboardButton(text="Завершить", callback_data="g_finish")
        ]
    ])

def get_progress_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="g_reset_progress")]
    ])

def get_reset_confirmation_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, сбросить", callback_data="g_confirm_reset_yes")],
        [InlineKeyboardButton(text="Назад", callback_data="g_confirm_reset_no")]
    ])

MIN_DURATION_BY_LEVEL = {
    "beginner": 30,
    "intermediate": 45,
    "advanced": 60
}

def text_similarity(original: str, recognized: str, threshold: float = 0.5) -> bool:
    clean_orig = re.sub(r'[^\w\s]', '', original).lower().split()
    clean_orig = [w for w in clean_orig if not re.search(r'[а-яА-Я]', w)]
    clean_recog = re.sub(r'[^\w\s]', '', recognized).lower().split()
    clean_recog = [w for w in clean_recog if not re.search(r'[а-яА-Я]', w)]
    if not clean_orig:
        return False
    common = set(clean_orig) & set(clean_recog)
    similarity = len(common) / len(clean_orig)
    logger.info(f"Схожесть текстов (без русских слов): {similarity:.2f}")
    return similarity >= threshold

async def hide_progress_buttons(message_or_callback, state: FSMContext):
    data = await state.get_data()
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            if hasattr(message_or_callback, 'bot'):
                chat_id = message_or_callback.chat.id
                bot = message_or_callback.bot
            else:
                chat_id = message_or_callback.message.chat.id
                bot = message_or_callback.message.bot
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Не удалось скрыть кнопку сброса: {e}")
    
    last_task_msg_id = data.get("last_task_msg_id")
    if last_task_msg_id:
        try:
            if hasattr(message_or_callback, 'bot'):
                chat_id = message_or_callback.chat.id
                bot = message_or_callback.bot
            else:
                chat_id = message_or_callback.message.chat.id
                bot = message_or_callback.message.bot
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=last_task_msg_id,
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Не удалось скрыть кнопки задания: {e}")

@router.message(F.text.startswith('/'), GovorenieStates.choosing_type,
                GovorenieStates.choosing_level, GovorenieStates.waiting_voice,
                GovorenieStates.showing_progress, GovorenieStates.confirm_reset)
async def handle_command_during_govorenie(message: Message, state: FSMContext):
    from handlers.start import show_main_menu  # локальный импорт
    await hide_progress_buttons(message, state)
    await message.answer("Практика завершена")
    await state.clear()
    await show_main_menu(message, edit=False)

@router.callback_query(F.data == "start_govorenie")
async def start_govorenie_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(GovorenieStates.choosing_type)
    await show_task_types(callback.message, edit=True)

async def show_task_types(message: Message, edit: bool = False):
    text = "🎤 Говорение\n\nВыберите тип задания:"
    keyboard = get_types_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("g_type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_type = callback.data.split("_")[2]
    await state.update_data(task_type=task_type)
    await state.set_state(GovorenieStates.choosing_level)
    text = "Выберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="HTML")

@router.callback_query(F.data.startswith("g_level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    level = callback.data.split("_")[2]
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")

    tasks = ALL_TASKS.get(task_type, {}).get(level, [])
    if not tasks:
        await callback.message.edit_text(f"Заданий для {task_type} уровня {level} пока нет.")
        return

    await init_govorenie_session(user_id, task_type, level)

    current_id = await get_govorenie_task_id(user_id, task_type, level)
    current_task = next((t for t in tasks if t.get("id") == current_id), None)
    if current_task is None:
        current_task = tasks[0]
        current_id = current_task["id"]

    await state.update_data(
        user_id=user_id,
        task_type=task_type,
        level=level,
        tasks=tasks,
        current_task=current_task,
        current_id=current_id,
        last_task_msg_id=None,
        progress_msg_id=None
    )

    try:
        await show_progress_card(callback.message, state, edit=True)
    except Exception as e:
        logger.error(f"Ошибка в show_progress_card: {e}")
        await callback.message.answer("Произошла ошибка при показе прогресса. Попробуйте заново.")
        return

    try:
        await show_task(callback.message, state, edit=False)
    except Exception as e:
        logger.error(f"Ошибка в show_task: {e}")
        await callback.message.answer("Произошла ошибка при показе задания. Попробуйте заново.")
        return

async def show_progress_card(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        logger.error("user_id not found in state")
        return
    task_type = data.get("task_type")
    level = data.get("level")

    total_answered, total_score, session_answered, session_score = await get_govorenie_stats(user_id, task_type, level)

    type_names = {
        "reading": "📖 Чтение вслух",
        "fluency": "⏱ Беглость",
        "interview": "🎤 Интервью"
    }
    level_names = {
        "beginner": "🌱 Новичок",
        "intermediate": "📚 Любитель",
        "advanced": "🎓 Эксперт"
    }

    mode_text = type_names.get(task_type, task_type)
    level_text = level_names.get(level, level)

    if total_answered > 0:
        avg_score = round(total_score / total_answered, 1)
    else:
        avg_score = 0

    card_text = (
        f"<b>Режим:</b> {mode_text}\n"
        f"<b>Уровень:</b> {level_text}\n"
    )

    if task_type in ["reading", "fluency"]:
        card_text += f"\n<i>Длина голосового ответа не должна превышать 3 минуты</i>\n"

    if task_type == "interview":
        if level == "advanced":
            card_text += f"\n<i>Длина голосового ответа не должна превышать 3 минуты</i>\n"
        else:
            card_text += f"\n<i>Длина голосового ответа не должна превышать 2 минуты</i>\n"
        card_text += (
            f"\n<i>Как должен выглядеть ваш ответ:</i>\n"
            f"<i>1. Начните с краткого вступления и завершите заключением.</i>\n"
            f"<i>2. Используйте слова-связки (however, moreover, for example, in addition и т. д.) — они делают речь логичной и связной.</i>\n"
            f"<i>3. Перед ответом зачитайте вопрос, затем дайте развёрнутый ответ, стараясь уложиться в отведённое время и охватить все пункты.</i>\n"
        )

    card_text += f"\nВаш средний балл: {avg_score}/5"

    keyboard = get_progress_keyboard()
    if edit:
        sent = await message.edit_text(card_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        sent = await message.answer(card_text, reply_markup=keyboard, parse_mode="HTML")

    await state.update_data(progress_msg_id=sent.message_id)
    await state.set_state(GovorenieStates.showing_progress)

async def show_task(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    if not task:
        await message.answer("Ошибка: задание не найдено.")
        return

    if task_type == "reading" and "text" not in task:
        logger.error(f"Задание чтения без поля 'text': {task}")
        await message.answer("Ошибка в структуре задания (чтение).")
        return
    if task_type == "fluency" and "topic" not in task:
        logger.error(f"Задание беглости без поля 'topic': {task}")
        await message.answer("Ошибка в структуре задания (беглость).")
        return
    if task_type == "interview" and "questions" not in task:
        logger.error(f"Задание интервью без поля 'questions': {task}")
        await message.answer("Ошибка в структуре задания (интервью).")
        return

    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
        await state.update_data(last_task_msg_id=None)

    if task_type == "reading":
        text = f"{task.get('instruction', '')}\n\n<i>{task['text']}</i>"
    elif task_type == "fluency":
        text = f"{task.get('instruction', '')}\n\n<b>{task['topic']}</b>"
    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        text = f"{task.get('instruction', '')}\n\n{questions}"
    else:
        text = "Неизвестный тип задания."

    keyboard = get_action_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(last_task_msg_id=sent_msg.message_id)

    await state.set_state(GovorenieStates.waiting_voice)

@router.callback_query(F.data == "g_reset_progress")
async def reset_progress_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task_type = data.get("task_type")
    if not task_type:
        await callback.message.answer("Ошибка: тип задания не найден. Начните заново.")
        return

    progress_msg_id = data.get("progress_msg_id")
    if not progress_msg_id:
        await callback.message.answer("Ошибка: карточка прогресса не найдена.")
        return

    text = "Вы уверены? Средний балл будет обнулен. Все задания будут даны с самого начала."
    keyboard = get_reset_confirmation_keyboard()
    try:
        await callback.bot.edit_text(
            text,
            chat_id=callback.message.chat.id,
            message_id=progress_msg_id,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось отредактировать карточку: {e}")
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await state.set_state(GovorenieStates.confirm_reset)

@router.callback_query(F.data == "g_confirm_reset_yes", GovorenieStates.confirm_reset)
async def reset_progress_yes(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])

    if not tasks:
        await callback.message.answer("Нет заданий для сброса.")
        await state.clear()
        return

    await reset_govorenie_progress(user_id, task_type, level)
    await state.update_data(current_id=0, current_task=tasks[0], last_task_msg_id=None, progress_msg_id=None)

    await callback.message.edit_text("Прогресс сброшен. Задания даны с начала.", reply_markup=None)

    await show_progress_card(callback.message, state, edit=False)
    await show_task(callback.message, state, edit=False)

@router.callback_query(F.data == "g_confirm_reset_no", GovorenieStates.confirm_reset)
async def reset_progress_no(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_progress_card(callback.message, state, edit=True)
    await show_task(callback.message, state, edit=True)

@router.message(GovorenieStates.waiting_voice, F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    logger.info(f"handle_voice_message начат, user={message.from_user.id}")
    user_id = message.from_user.id
    data = await state.get_data()
    task = data.get("current_task")
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])
    current_id = data.get("current_id", 0)

    if not task:
        logger.error("Задание не найдено в состоянии")
        await message.answer("Ошибка: задание не найдено. Начните заново.")
        await state.clear()
        return

    voice: Voice = message.voice
    duration = voice.duration
    logger.info(f"Длительность: {duration} сек")

    if task_type == "reading":
        if duration < 20:
            await message.answer("Слишком коротко (минимум 20 секунд).")
            return
        if duration > 180:
            await message.answer("Голосовое не подходит по условиям задания, перезапишите на более короткую длительность.")
            return
    elif task_type == "fluency":
        min_duration = MIN_DURATION_BY_LEVEL.get(level, 60)
        if duration < min_duration:
            await message.answer(f"По условиям задания не менее {min_duration} секунд. Пожалуйста, перезапишите.")
            return
        if duration > 180:
            await message.answer("Голосовое не подходит по условиям задания, перезапишите на более короткую длительность.")
            return
    elif task_type == "interview":
        if duration < 20:
            await message.answer("По условиям задания не менее 20 секунд. Пожалуйста, перезапишите.")
            return
        if level == "advanced":
            if duration > 180:
                await message.answer("Голосовое не подходит по условиям задания, перезапишите на более короткую длительность.")
                return
        else:
            if duration > 120:
                await message.answer("Голосовое не подходит по условиям задания, перезапишите на более короткую длительность.")
                return

    file_id = voice.file_id
    file = await message.bot.get_file(file_id)
    file_path = file.file_path
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            await message.bot.download_file(file_path, tmp.name)
            tmp_path = tmp.name
        logger.info(f"Файл скачан: {tmp_path}")

        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        user_text = await speech_to_text(tmp_path)
        logger.info(f"Распознанный текст: {user_text[:100]}...")
    except Exception as e:
        logger.error(f"Ошибка распознавания: {e}")
        await message.answer("Не удалось распознать голос. Попробуйте говорить чётче.")
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not re.search(r'[a-zA-Z]', user_text):
        await message.answer("Отсутствует речь в голосовом, пожалуйста, перезапишите.")
        return

    rus_ratio = len(re.findall(r'[а-яА-Я]', user_text)) / max(1, len(user_text))
    if rus_ratio > 0.5:
        await message.answer("Ваш ответ должен быть на английском языке. Пожалуйста, перезапишите.")
        return

    if task_type == "reading":
        original = task.get('text', '')
        if original and not text_similarity(original, user_text, threshold=0.5):
            await message.answer(
                "Похоже, вы читаете не тот текст. Пожалуйста, внимательно прочитайте задание и попробуйте ещё раз."
            )
            return

    logger.info("Вызов check_govorenie...")
    try:
        feedback, score = await check_govorenie(
            task=task,
            task_type=task_type,
            user_text=user_text,
            level=level,
            duration=duration
        )
        logger.info(f"Ответ получен: оценка={score}, фидбек={feedback[:50]}...")
    except Exception as e:
        logger.error(f"Ошибка ИИ: {e}")
        await message.answer("Ошибка при обращении к ИИ. Попробуйте позже.")
        return

    criteria_keywords = [
        'Содержание ответа:', 'Полнота ответов:', 'Грамматика:', 'Словарный запас:',
        'Аргументация:', 'Точность:', 'Темп:', 'Советы:', 'Соответствие теме:'
    ]
    for keyword in criteria_keywords:
        feedback = feedback.replace(keyword, f'<b>{keyword}</b>')

    if "не соответствует теме" in feedback or "совершенно не соответствует теме" in feedback:
        await message.answer(
            f"{feedback}",
            parse_mode="HTML"
        )
        await message.answer("Попробуйте ещё раз, запишите ответ на это же задание.")
        return

    await update_govorenie_stats(user_id, task_type, level, score)

    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
        await state.update_data(last_task_msg_id=None)

    await message.answer(
        f"{feedback}\n\n<b>Оценка: {score}/5</b>",
        parse_mode="HTML"
    )
    logger.info("Фидбек отправлен")

    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await show_progress_card(message, state, edit=True)
        except Exception as e:
            logger.error(f"Не удалось обновить карточку: {e}")

    await go_to_next_task(message, state, user_id, task_type, level, current_id, tasks)

async def go_to_next_task(message: Message, state: FSMContext, user_id: int, task_type: str, level: str, current_id: int, tasks: list):
    next_task = next((t for t in tasks if t.get("id") == current_id + 1), None)
    if next_task is None:
        next_task = tasks[0]
    await set_govorenie_task_id(user_id, task_type, level, next_task["id"])
    await state.update_data(
        current_task=next_task,
        current_id=next_task["id"]
    )
    await show_task(message, state, edit=False)

@router.callback_query(F.data == "g_next_task")
async def next_task_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])
    current_id = data.get("current_id", 0)
    user_id = callback.from_user.id

    if not tasks:
        await callback.message.answer("Нет заданий.")
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    next_task = next((t for t in tasks if t.get("id") == current_id + 1), None)
    if next_task is None:
        next_task = tasks[0]
    await set_govorenie_task_id(user_id, task_type, level, next_task["id"])
    await state.update_data(
        current_task=next_task,
        current_id=next_task["id"]
    )
    await show_task(callback.message, state, edit=False)

@router.callback_query(F.data == "g_finish")
async def finish_govorenie(callback: CallbackQuery, state: FSMContext):
    from handlers.start import show_main_menu
    await callback.answer()
    await hide_progress_buttons(callback, state)
    
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")

    total_answered, total_score, session_answered, session_score = await get_govorenie_stats(user_id, task_type, level)

    if session_answered > 0:
        avg_session = round(session_score / session_answered, 1)
        tasks_word = "задание" if session_answered == 1 else "задания" if 2 <= session_answered <= 4 else "заданий"
        await callback.message.answer(
            f"Сессия завершена! 🙌🏻\n"
            f"Вы выполнили {session_answered} {tasks_word}.\n"
            f"Средний балл за сессию: {avg_session}."
        )
    else:
        await callback.message.answer(
            "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
        )

    await state.clear()
    await show_main_menu(callback.message, edit=False)

@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(GovorenieStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_govorenie(callback: CallbackQuery, state: FSMContext):
    from handlers.start import show_main_menu
    await callback.answer()
    await hide_progress_buttons(callback, state)
    await state.clear()
    await show_main_menu(callback.message, edit=False)

@router.message(GovorenieStates.waiting_voice, ~F.voice)
async def handle_non_voice_in_govorenie(message: Message, state: FSMContext):
    await message.answer("Запишите и отправьте голосовое сообщение.")


# =====================================================================
# ФУНКЦИЯ ДЛЯ ВЫЗОВА ИЗ START.PY
# =====================================================================
async def start_govorenie(callback: CallbackQuery, state: FSMContext):
    """
    Запускает режим Говорение из внешнего вызова (например, из start.py).
    """
    await start_govorenie_mode(callback, state)