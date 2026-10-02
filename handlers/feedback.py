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
MY_TELEGRAM = os.getenv("MY_TELEGRAM", "")


class SurveyStates(StatesGroup):
    q1 = State()  # goal
    q2 = State()  # price
    q3 = State()  # modes
    q4 = State()  # tasks
    q5 = State()  # improve
    q6 = State()  # contact


INTRO_TEXT = (
    "Спасибо, что нашёл(нашла) время.\n\n"
    "6 коротких вопросов — это займёт около минуты.\n"
    "На каждом шаге можно нажать «Пропустить», если не хочется отвечать."
)


def kb_begin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать", callback_data="survey_begin")],
    ])


def kb_goal():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Хочу говорить свободнее", callback_data="survey_goal_speak")],
        [InlineKeyboardButton(text="Готовлюсь к экзамену / работе", callback_data="survey_goal_exam")],
        [InlineKeyboardButton(text="Ради интереса", callback_data="survey_goal_fun")],
        [InlineKeyboardButton(text="Собираюсь переезжать / путешествовать", callback_data="survey_goal_travel")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_price():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Всё устраивает", callback_data="survey_price_ok")],
        [InlineKeyboardButton(text="Дорого", callback_data="survey_price_expensive")],
        [InlineKeyboardButton(text="Не понимаю, что входит", callback_data="survey_price_unclear")],
        [InlineKeyboardButton(text="Хочу больше минут за эти деньги", callback_data="survey_price_more")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_modes():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Общение с AI", callback_data="survey_modes_chat")],
        [InlineKeyboardButton(text="Ролевые игры", callback_data="survey_modes_roleplay")],
        [InlineKeyboardButton(text="Тренажёры", callback_data="survey_modes_trainers")],
        [InlineKeyboardButton(text="Всё нравится", callback_data="survey_modes_all")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_tasks():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очень нравятся", callback_data="survey_tasks_love")],
        [InlineKeyboardButton(text="Нормальные, но есть что улучшить", callback_data="survey_tasks_ok")],
        [InlineKeyboardButton(text="Так себе", callback_data="survey_tasks_meh")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_improve():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Больше голоса", callback_data="survey_improve_voice")],
        [InlineKeyboardButton(text="Больше заданий", callback_data="survey_improve_tasks")],
        [InlineKeyboardButton(text="Снизить цену", callback_data="survey_improve_price")],
        [InlineKeyboardButton(text="Ничего, всё ок", callback_data="survey_improve_ok")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="survey_skip")],
    ])


def kb_contact():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, хочу", callback_data="survey_contact_yes")],
        [InlineKeyboardButton(text="Нет, спасибо", callback_data="survey_contact_no")],
    ])


async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass


async def hide_buttons(callback: CallbackQuery):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.debug(f"hide_buttons: {e}")


# ---------- ВХОД ----------

@router.callback_query(F.data == "start_survey")
async def survey_intro(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    try:
        await state.clear()
    except Exception as e:
        logger.error(f"[survey_intro] state.clear: {e}")
    logger.info(f"[survey_intro] user={callback.from_user.id}")
    await callback.message.answer(INTRO_TEXT, reply_markup=kb_begin())


@router.callback_query(F.data == "survey_begin")
async def survey_begin(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    logger.info(f"[survey_begin] user={callback.from_user.id}")
    await state.set_state(SurveyStates.q1)
    await callback.message.answer("1 / 6. Что тебя привело в бот?", reply_markup=kb_goal())


# ---------- Q1: goal ----------

@router.callback_query(SurveyStates.q1, F.data.startswith("survey_goal_"))
async def q1_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    await state.update_data(goal=callback.data.replace("survey_goal_", ""))
    await state.set_state(SurveyStates.q2)
    await callback.message.answer("2 / 6. Устраивает ли тебя стоимость подписок?", reply_markup=kb_price())


# ---------- Q2: price ----------

@router.callback_query(SurveyStates.q2, F.data.startswith("survey_price_"))
async def q2_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    await state.update_data(price=callback.data.replace("survey_price_", ""))
    await state.set_state(SurveyStates.q3)
    await callback.message.answer("3 / 6. Какие режимы для тебя главные в боте?", reply_markup=kb_modes())


# ---------- Q3: modes ----------

@router.callback_query(SurveyStates.q3, F.data.startswith("survey_modes_"))
async def q3_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    await state.update_data(modes=callback.data.replace("survey_modes_", ""))
    await state.set_state(SurveyStates.q4)
    await callback.message.answer("4 / 6. Нравятся ли тебе задания в этих режимах?", reply_markup=kb_tasks())


# ---------- Q4: tasks ----------

@router.callback_query(SurveyStates.q4, F.data.startswith("survey_tasks_"))
async def q4_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    await state.update_data(tasks=callback.data.replace("survey_tasks_", ""))
    await state.set_state(SurveyStates.q5)
    await callback.message.answer("5 / 6. Что бы улучшил(а)?", reply_markup=kb_improve())


# ---------- Q5: improve ----------

@router.callback_query(SurveyStates.q5, F.data.startswith("survey_improve_"))
async def q5_answer(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    await state.update_data(improve=callback.data.replace("survey_improve_", ""))
    await state.set_state(SurveyStates.q6)
    await callback.message.answer("6 / 6. Хочешь, чтобы мы связались с тобой лично?", reply_markup=kb_contact())


# ---------- SKIP ----------

SKIP_MAP = {
    SurveyStates.q1.state: ("2 / 6. Устраивает ли тебя стоимость подписок?", kb_price, SurveyStates.q2),
    SurveyStates.q2.state: ("3 / 6. Какие режимы для тебя главные в боте?", kb_modes, SurveyStates.q3),
    SurveyStates.q3.state: ("4 / 6. Нравятся ли тебе задания в этих режимах?", kb_tasks, SurveyStates.q4),
    SurveyStates.q4.state: ("5 / 6. Что бы улучшил(а)?", kb_improve, SurveyStates.q5),
    SurveyStates.q5.state: ("6 / 6. Хочешь, чтобы мы связались с тобой лично?", kb_contact, SurveyStates.q6),
}


@router.callback_query(F.data == "survey_skip")
async def survey_skip(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    current = await state.get_state()
    logger.info(f"[survey_skip] user={callback.from_user.id} state={current}")

    if current in SKIP_MAP:
        text, kb_func, next_state = SKIP_MAP[current]
        await state.set_state(next_state)
        await callback.message.answer(text, reply_markup=kb_func())
    else:
        await state.set_state(SurveyStates.q1)
        await callback.message.answer("1 / 6. Что тебя привело в бот?", reply_markup=kb_goal())


# ---------- Q6: contact ----------

@router.callback_query(SurveyStates.q6, F.data == "survey_contact_yes")
async def q6_yes(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    await state.update_data(contact="yes")
    await finish_survey(callback, state, wants_contact=True, direct=False)


@router.callback_query(SurveyStates.q6, F.data == "survey_contact_no")
async def q6_no(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    await state.update_data(contact="no")
    await finish_survey(callback, state, wants_contact=False, direct=False)


# ---------- Прямая кнопка «Связаться» ----------

@router.callback_query(F.data == "start_contact")
async def start_contact(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    await hide_buttons(callback)
    logger.info(f"[start_contact] user={callback.from_user.id}")
    await state.update_data(contact="yes_direct")
    await finish_survey(callback, state, wants_contact=True, direct=True)


# ---------- Финал ----------

async def finish_survey(callback: CallbackQuery, state: FSMContext, wants_contact: bool, direct: bool):
    data = await state.get_data()
    user_id = callback.from_user.id

    try:
        await save_feedback(user_id, data, wants_contact)
    except Exception as e:
        logger.error(f"Ошибка сохранения фидбека для {user_id}: {e}")

    await state.clear()

    if wants_contact:
        word = "по связи" if direct else "по опросу"
        if MY_TELEGRAM:
            msg = (
                "Спасибо! Мы свяжемся с тобой в ближайшее время.\n\n"
                f"Напиши нам первым, пожалуйста: @{MY_TELEGRAM}\n"
                f"И укажи «{word}» — чтобы мы сразу поняли, что это ты."
            )
        else:
            msg = "Спасибо! Мы свяжемся с тобой в ближайшее время."
        await callback.message.answer(msg)
    else:
        await callback.message.answer("Спасибо за ответы! Это правда помогает.")

    await notify_admin(callback, user_id, data, wants_contact, direct)


async def save_feedback(user_id: int, data: dict, wants_contact: bool):
    conn = await get_connection()
    try:
        await conn.execute("""
            INSERT INTO feedback
                (user_id, q1_goal, q3_price, q4_modes, q4_tasks, q5_improve, q6_contact, wants_contact, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, EXTRACT(EPOCH FROM NOW())::BIGINT)
        """,
            user_id,
            data.get("goal"),
            data.get("price"),
            data.get("modes"),
            data.get("tasks"),
            data.get("improve"),
            data.get("contact"),
            wants_contact,
        )
    finally:
        await conn.close()


async def notify_admin(callback: CallbackQuery, user_id: int, data: dict, wants_contact: bool, direct: bool):
    if not ADMIN_ID:
        logger.warning("ADMIN_ID не задан — алерт не отправлен")
        return

    username = callback.from_user.username or "—"
    first_name = callback.from_user.first_name or ""

    if wants_contact and direct:
        header = "🔔 <b>Хочет связаться (без опроса)</b>"
    elif wants_contact and not direct:
        header = "🔔 <b>Хочет связаться (после опроса)</b>"
    else:
        header = "📋 <b>Прошёл опрос (без связи)</b>"

    text = (
        f"{header}\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Имя: {first_name}\n"
        f"Username: @{username}\n\n"
        "<b>Ответы:</b>\n"
        f"• Цель: {data.get('goal', '—')}\n"
        f"• Цена: {data.get('price', '—')}\n"
        f"• Режимы: {data.get('modes', '—')}\n"
        f"• Задания: {data.get('tasks', '—')}\n"
        f"• Улучшить: {data.get('improve', '—')}\n\n"
        f"Профиль: /user/{user_id}"
    )
    if username == "—":
        text += f"\n\n⚠️ Username не указан. Открыть: <code>tg://user?id={user_id}</code>"

    try:
        await callback.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось отправить алерт админу: {e}")