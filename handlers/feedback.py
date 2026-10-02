import logging
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.db import get_connection

logger = logging.getLogger(__name__)
router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", 0) or 0)


class SurveyStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()
    q6 = State()


INTRO_TEXT = (
    "Спасибо, что нашёл(нашла) время.\n\n"
    "6 коротких вопросов — это займёт около минуты.\n"
    "На каждом шаге можно нажать «Пропустить», если не хочется отвечать."
)


def kb_begin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать", callback_data="survey_begin")],
    ])


def kb_q1():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Хочу говорить свободнее", callback_data="survey_q1_speak")],
        [InlineKeyboardButton(text="Готовлюсь к экзамену / работе", callback_data="survey_q1_exam")],
        [InlineKeyboardButton(text="Ради интереса", callback_data="survey_q1_fun")],
        [InlineKeyboardButton(text="Собираюсь переезжать / путешествовать", callback_data="survey_q1_travel")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_q2():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мало времени", callback_data="survey_q2_time")],
        [InlineKeyboardButton(text="Не знаю, с чего начать", callback_data="survey_q2_start")],
        [InlineKeyboardButton(text="Не вижу прогресса", callback_data="survey_q2_progress")],
        [InlineKeyboardButton(text="Ничего не мешает", callback_data="survey_q2_nothing")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_q3():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Всё устраивает", callback_data="survey_q3_ok")],
        [InlineKeyboardButton(text="Дорого", callback_data="survey_q3_expensive")],
        [InlineKeyboardButton(text="Не понимаю, что входит", callback_data="survey_q3_unclear")],
        [InlineKeyboardButton(text="Хочу больше минут за эти деньги", callback_data="survey_q3_more")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_q4():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Общение с AI", callback_data="survey_q4_chat")],
        [InlineKeyboardButton(text="Ролевые игры", callback_data="survey_q4_roleplay")],
        [InlineKeyboardButton(text="Тренажёры", callback_data="survey_q4_trainers")],
        [InlineKeyboardButton(text="Всё нравится", callback_data="survey_q4_all")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_q5():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Больше голоса", callback_data="survey_q5_voice")],
        [InlineKeyboardButton(text="Больше заданий", callback_data="survey_q5_tasks")],
        [InlineKeyboardButton(text="Снизить цену", callback_data="survey_q5_price")],
        [InlineKeyboardButton(text="Ничего, всё ок", callback_data="survey_q5_ok")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_q6():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, хочу", callback_data="survey_q6_yes")],
        [InlineKeyboardButton(text="Нет, спасибо", callback_data="survey_q6_no")],
    ])


async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass


# ---------- ВХОД В ОПРОС ----------

@router.callback_query(F.data == "start_survey")
async def survey_intro(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    try:
        await state.clear()
    except Exception as e:
        logger.error(f"[survey_intro] state.clear: {e}")
    logger.info(f"[survey_intro] user={callback.from_user.id}")
    try:
        await callback.message.answer(INTRO_TEXT, reply_markup=kb_begin())
    except Exception as e:
        logger.error(f"[survey_intro] answer: {e}")


@router.callback_query(F.data == "survey_begin")
async def survey_begin(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    logger.info(f"[survey_begin] user={callback.from_user.id}")
    try:
        await state.set_state(SurveyStates.q1)
    except Exception as e:
        logger.error(f"[survey_begin] set_state: {e}")
    try:
        await callback.message.answer(
            "1 / 6. Что тебя привело в бот?",
            reply_markup=kb_q1(),
        )
    except Exception as e:
        logger.error(f"[survey_begin] answer: {e}")


# ---------- Q1 ----------

@router.callback_query(SurveyStates.q1, F.data.startswith("survey_q1_"))
async def q1_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    answer = callback.data.replace("survey_q1_", "")
    await state.update_data(q1=answer)
    await state.set_state(SurveyStates.q2)
    await callback.message.answer(
        "2 / 6. Что мешает заниматься регулярно?",
        reply_markup=kb_q2(),
    )


# ---------- Q2 ----------

@router.callback_query(SurveyStates.q2, F.data.startswith("survey_q2_"))
async def q2_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    answer = callback.data.replace("survey_q2_", "")
    await state.update_data(q2=answer)
    await state.set_state(SurveyStates.q3)
    await callback.message.answer(
        "3 / 6. Устраивает ли тебя стоимость подписок?",
        reply_markup=kb_q3(),
    )


# ---------- Q3 ----------

@router.callback_query(SurveyStates.q3, F.data.startswith("survey_q3_"))
async def q3_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    answer = callback.data.replace("survey_q3_", "")
    await state.update_data(q3=answer)
    await state.set_state(SurveyStates.q4)
    await callback.message.answer(
        "4 / 6. Какие режимы для тебя главные в боте?",
        reply_markup=kb_q4(),
    )


# ---------- Q4 ----------

@router.callback_query(SurveyStates.q4, F.data.startswith("survey_q4_"))
async def q4_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    answer = callback.data.replace("survey_q4_", "")
    await state.update_data(q4=answer)
    await state.set_state(SurveyStates.q5)
    await callback.message.answer(
        "5 / 6. Что бы улучшил(а)?",
        reply_markup=kb_q5(),
    )


# ---------- Q5 ----------

@router.callback_query(SurveyStates.q5, F.data.startswith("survey_q5_"))
async def q5_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    answer = callback.data.replace("survey_q5_", "")
    await state.update_data(q5=answer)
    await state.set_state(SurveyStates.q6)
    await callback.message.answer(
        "6 / 6. Хочешь, чтобы мы связались с тобой лично?",
        reply_markup=kb_q6(),
    )


# ---------- SKIP (работает в любом из состояний q1..q5) ----------

SKIP_MAP = {
    SurveyStates.q1.state: ("2 / 6. Что мешает заниматься регулярно?", kb_q2, SurveyStates.q2),
    SurveyStates.q2.state: ("3 / 6. Устраивает ли тебя стоимость подписок?", kb_q3, SurveyStates.q3),
    SurveyStates.q3.state: ("4 / 6. Какие режимы для тебя главные в боте?", kb_q4, SurveyStates.q4),
    SurveyStates.q4.state: ("5 / 6. Что бы улучшил(а)?", kb_q5, SurveyStates.q5),
    SurveyStates.q5.state: ("6 / 6. Хочешь, чтобы мы связались с тобой лично?", kb_q6, SurveyStates.q6),
}


@router.callback_query(F.data == "survey_skip")
async def survey_skip(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    current = await state.get_state()
    logger.info(f"[survey_skip] user={callback.from_user.id} state={current}")

    if current in SKIP_MAP:
        text, kb_func, next_state = SKIP_MAP[current]
        await state.set_state(next_state)
        await callback.message.answer(text, reply_markup=kb_func())
    else:
        # Если state не сработал — всё равно отправим Q1
        await state.set_state(SurveyStates.q1)
        await callback.message.answer(
            "1 / 6. Что тебя привело в бот?",
            reply_markup=kb_q1(),
        )


# ---------- Q6 ----------

@router.callback_query(SurveyStates.q6, F.data == "survey_q6_yes")
async def q6_yes(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await state.update_data(q6="yes")
    await finish_survey(callback, state, wants_contact=True)


@router.callback_query(SurveyStates.q6, F.data == "survey_q6_no")
async def q6_no(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await state.update_data(q6="no")
    await finish_survey(callback, state, wants_contact=False)


# ---------- Отдельная кнопка «Связаться» ----------

@router.callback_query(F.data == "start_contact")
async def start_contact(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    logger.info(f"[start_contact] user={callback.from_user.id}")
    await state.update_data(q6="yes_direct")
    await finish_survey(callback, state, wants_contact=True)


# ---------- Финал ----------

async def finish_survey(callback: CallbackQuery, state: FSMContext, wants_contact: bool):
    data = await state.get_data()
    user_id = callback.from_user.id

    try:
        await save_feedback(user_id, data, wants_contact)
    except Exception as e:
        logger.error(f"Ошибка сохранения фидбека для {user_id}: {e}")

    await state.clear()

    if wants_contact:
        await callback.message.answer("Спасибо! Мы свяжемся с тобой в ближайшее время.")
        await notify_admin(callback, user_id, data)
    else:
        await callback.message.answer("Спасибо за ответы! Это правда помогает.")


async def save_feedback(user_id: int, data: dict, wants_contact: bool):
    conn = await get_connection()
    try:
        await conn.execute("""
            INSERT INTO feedback
                (user_id, q1_goal, q2_barrier, q3_price, q4_modes, q5_improve, q6_contact, wants_contact, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, EXTRACT(EPOCH FROM NOW())::BIGINT)
        """,
            user_id,
            data.get("q1"),
            data.get("q2"),
            data.get("q3"),
            data.get("q4"),
            data.get("q5"),
            data.get("q6"),
            wants_contact,
        )
    finally:
        await conn.close()


async def notify_admin(callback: CallbackQuery, user_id: int, data: dict):
    if not ADMIN_ID:
        logger.warning("ADMIN_ID не задан — алерт не отправлен")
        return

    username = callback.from_user.username or "—"
    first_name = callback.from_user.first_name or ""
    text = (
        "🔔 <b>Пользователь хочет связаться</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Имя: {first_name}\n"
        f"Username: @{username}\n\n"
        "<b>Ответы:</b>\n"
        f"• Цель: {data.get('q1', '—')}\n"
        f"• Мешает: {data.get('q2', '—')}\n"
        f"• Цена: {data.get('q3', '—')}\n"
        f"• Режимы: {data.get('q4', '—')}\n"
        f"• Улучшить: {data.get('q5', '—')}\n\n"
        f"Профиль: /user/{user_id}"
    )
    try:
        await callback.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось отправить алерт админу: {e}")