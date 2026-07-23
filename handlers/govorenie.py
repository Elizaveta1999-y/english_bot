import json
import os
import tempfile
import re
import random
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

logger = logging.getLogger(__name__)
router = Router()

# ---------- Загрузка заданий ----------
TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/govorenie_tasks.json")

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

ALL_TASKS = load_tasks()

# ---------- Состояния FSM ----------
class GovorenieStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_voice = State()
    showing_progress = State()
    confirm_reset = State()

# ---------- Клавиатуры ----------
def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Чтение вслух", callback_data="g_type_reading")],
        [InlineKeyboardButton(text="⏱ Беглость (1 мин)", callback_data="g_type_fluency")],
        [InlineKeyboardButton(text="🎤 Интервью", callback_data="g_type_interview")],
        [InlineKeyboardButton(text="🎲 Случайный", callback_data="g_type_random")],
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
            InlineKeyboardButton(text="Показать ответ", callback_data="g_show_sample"),
            InlineKeyboardButton(text="Следующее задание", callback_data="g_next_task")
        ],
        [
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

# ============================================================
# 🔥 НОВЫЙ СЛОВАРЬ – минимальная длительность для беглости по уровням
# ============================================================
MIN_DURATION_BY_LEVEL = {
    "beginner": 30,
    "intermediate": 45,
    "expert": 60,
    "advanced": 60
}

# ============================================================
# 🔥 ФУНКЦИЯ – проверка схожести текстов
# ============================================================
def text_similarity(original: str, recognized: str, threshold: float = 0.5) -> bool:
    """
    Проверяет, достаточно ли слов из оригинального текста присутствует в распознанном.
    Возвращает True, если процент совпадения >= threshold.
    """
    clean_orig = re.sub(r'[^\w\s]', '', original).lower().split()
    clean_recog = re.sub(r'[^\w\s]', '', recognized).lower().split()
    if not clean_orig:
        return False
    common = set(clean_orig) & set(clean_recog)
    similarity = len(common) / len(clean_orig)
    logger.info(f"Схожесть текстов: {similarity:.2f}")
    return similarity >= threshold

# ---------- ВХОД ----------
@router.callback_query(F.data == "start_govorenie")
async def start_govorenie_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(GovorenieStates.choosing_type)
    await show_task_types(callback.message, edit=True)

async def show_task_types(message: Message, edit: bool = False):
    text = "🎤 Говорение\n\nВыберите тип задания:"
    keyboard = get_types_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ---------- Выбор типа ----------
@router.callback_query(F.data.startswith("g_type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_type = callback.data.split("_")[2]
    await state.update_data(task_type=task_type)
    await state.set_state(GovorenieStates.choosing_level)
    text = f"Вы выбрали тип: *{task_type.upper()}*.\nТеперь выберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

# ---------- Выбор уровня ----------
@router.callback_query(F.data.startswith("g_level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    level = callback.data.split("_")[2]
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")

    if task_type == "random":
        possible_types = ["reading", "fluency", "interview"]
        task_type = random.choice(possible_types)
        await state.update_data(task_type=task_type)

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
        logger.info("✅ Карточка прогресса показана")
    except Exception as e:
        logger.error(f"❌ Ошибка в show_progress_card: {e}")
        await callback.message.answer("Произошла ошибка при показе прогресса. Попробуйте заново.")
        return

    try:
        await show_task(callback.message, state, edit=False)
        logger.info("✅ Задание показано, состояние переключено на waiting_voice")
    except Exception as e:
        logger.error(f"❌ Ошибка в show_task: {e}")
        await callback.message.answer("Произошла ошибка при показе задания. Попробуйте заново.")
        return

# ---------- Карточка прогресса ----------
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
        f"*Режим:* {mode_text}\n"
        f"*Уровень:* {level_text}\n\n"
        f"Напишите voice согласно заданию.\n\n"
        f"Ваш средний балл: {avg_score}/5"
    )

    keyboard = get_progress_keyboard()
    if edit:
        sent = await message.edit_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        sent = await message.answer(card_text, reply_markup=keyboard, parse_mode="Markdown")

    await state.update_data(progress_msg_id=sent.message_id)
    await state.set_state(GovorenieStates.showing_progress)

# ---------- Показ задания ----------
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
        text = f"{task.get('instruction', '')}\n\n_{task['text']}_"
    elif task_type == "fluency":
        text = f"{task.get('instruction', '')}\n\n**{task['topic']}**"
    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        text = f"{task.get('instruction', '')}\n\n{questions}"
    else:
        text = "Неизвестный тип задания."

    keyboard = get_action_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        sent_msg = await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        await state.update_data(last_task_msg_id=sent_msg.message_id)

    await state.set_state(GovorenieStates.waiting_voice)
    logger.info(f"Состояние установлено: {await state.get_state()}")

# ---------- Сброс прогресса ----------
@router.callback_query(F.data == "g_reset_progress")
async def reset_progress_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task_type = data.get("task_type")
    if not task_type:
        await callback.message.answer("Ошибка: тип задания не найден. Начните заново.")
        return

    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    text = "Вы уверены? Средний балл будет обнулен. Все задания будут даны с самого начала."
    keyboard = get_reset_confirmation_keyboard()
    await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
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

    await callback.message.edit_text("Прогресс обнулился. Задания даны с начала.", reply_markup=None)

    await show_progress_card(callback.message, state, edit=False)
    await show_task(callback.message, state, edit=False)

@router.callback_query(F.data == "g_confirm_reset_no", GovorenieStates.confirm_reset)
async def reset_progress_no(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.delete()
    await show_progress_card(callback.message, state, edit=False)
    await show_task(callback.message, state, edit=False)

# ---------- Обработка голосового ответа ----------
@router.message(GovorenieStates.waiting_voice, F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    logger.info(f"✅ handle_voice_message начат, user={message.from_user.id}")
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

    # ---------- Проверка минимальной длины ----------
    if duration < 2:
        await message.answer("Слишком коротко! Скажите что-то внятное (минимум 2 секунды).")
        return

    if task_type == "fluency":
        min_duration = MIN_DURATION_BY_LEVEL.get(level, 60)
        if duration < min_duration:
            await message.answer(f"Вы говорили только {duration} секунд. Нужно не менее {min_duration} секунд. Попробуйте ещё раз.")
            return

    if duration > 180:
        await message.answer("Слишком длинное сообщение (максимум 3 минуты). Сократите ответ.")
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

    if not user_text or len(user_text.strip()) < 3:
        await message.answer("Не удалось разобрать речь. Попробуйте говорить ближе к микрофону.")
        return

    if not re.search(r'[a-zA-Z]', user_text):
        if re.search(r'[а-яА-Я]', user_text):
            await message.answer("Ваше голосовое сообщение содержит русский текст. Пожалуйста, произнесите ответ на английском языке чётко и повторите попытку.")
        else:
            await message.answer("Не удалось распознать английскую речь. Пожалуйста, произнесите текст на английском языке чётко.")
        return

    stop_words_ru = ["ааа", "эээ", "м-м", "ну", "типа", "блин", "как бы", "это самое"]
    words = user_text.lower().split()
    if words:
        stop_count = sum(1 for w in words if w in stop_words_ru)
        if stop_count / len(words) > 0.3:
            await message.answer("Ваша речь содержит слишком много слов-паразитов. Постарайтесь говорить без них.")
            return

    # ---------- ЗАЩИТА ДЛЯ ЧТЕНИЯ ВСЛУХ ----------
    if task_type == "reading":
        original = task.get('text', '')
        if original and not text_similarity(original, user_text, threshold=0.5):
            await message.answer(
                "Похоже, вы читаете не тот текст. Пожалуйста, внимательно прочитайте задание и попробуйте ещё раз."
            )
            return

    # ---- ВЫЗОВ ИИ ----
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

    await message.answer(f"{feedback}\n\nОценка: {score}/5")
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

# ---------- Кнопки управления ----------
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

@router.callback_query(F.data == "g_show_sample")
async def show_sample_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    task = data.get("current_task")
    if not task:
        await callback.message.answer("Задание не найдено.")
        return

    sample = task.get("sample", "Пример ответа отсутствует.")
    await callback.message.answer(f"Пример ответа:\n\n{sample}")

    await callback.message.edit_reply_markup(reply_markup=None)

    task_type = data.get("task_type")
    level = data.get("level")
    tasks = data.get("tasks", [])
    current_id = data.get("current_id", 0)
    user_id = callback.from_user.id

    next_task = next((t for t in tasks if t.get("id") == current_id + 1), None)
    if next_task is None:
        next_task = tasks[0]
    await set_govorenie_task_id(user_id, task_type, level, next_task["id"])
    await state.update_data(
        current_task=next_task,
        current_id=next_task["id"]
    )
    await show_task(callback.message, state, edit=False)

# ---------- Завершение ----------
@router.callback_query(F.data == "g_finish")
async def finish_govorenie(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data = await state.get_data()
    task_type = data.get("task_type")
    level = data.get("level")

    total_answered, total_score, session_answered, session_score = await get_govorenie_stats(user_id, task_type, level)

    await callback.message.edit_reply_markup(reply_markup=None)
    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass

    if session_answered > 0:
        avg_session = round(session_score / session_answered, 1)
        await callback.message.answer(
            f"Сессия завершена! Вы выполнили {session_answered} заданий. "
            f"Средний балл за сессию: {avg_session}. Отличная работа! 💪"
        )
    else:
        await callback.message.answer(
            "Сессия завершена! Вы не ответили ни на одно задание. 🙌🏻"
        )

    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

# ---------- Навигация ----------
@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(GovorenieStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_govorenie(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    data = await state.get_data()
    last_msg_id = data.get("last_task_msg_id")
    if last_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    progress_msg_id = data.get("progress_msg_id")
    if progress_msg_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=progress_msg_id,
                reply_markup=None
            )
        except Exception:
            pass
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

# ---------- Обработка текстовых сообщений в режиме говорения ----------
@router.message(GovorenieStates.waiting_voice, F.text)
async def handle_text_in_govorenie(message: Message, state: FSMContext):
    await message.answer("В режиме говорения можно отвечать только голосовым сообщением. Пожалуйста, запишите голосовой ответ и отправьте его.")

# ---------- ОТЛАДОЧНЫЙ ХЕНДЛЕР ----------
@router.message(F.voice)
async def catch_all_voice(message: Message, state: FSMContext):
    current_state = await state.get_state()
    logger.warning(f"🔊 Поймано голосовое от {message.from_user.id}, состояние: {current_state}")
    await message.answer(f"Голосовое сообщение получено, но режим не активен (состояние: {current_state}). Начните заново.")