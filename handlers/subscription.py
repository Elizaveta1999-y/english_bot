import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from datetime import datetime
from utils.db import (
    get_user_profile,
    create_payment_record,
    get_user_pending_payments,
    activate_subscription_from_payment,
)
from services.yookassa import create_payment, get_payment_status
from data.users import get_user_state, set_user_state
import asyncio

logger = logging.getLogger(__name__)
router = Router()

PRICE_RUB = 999
DURATION_DAYS = 30

_bot_username_cache = None

async def _get_bot_username(bot):
    global _bot_username_cache
    if _bot_username_cache is None:
        me = await bot.get_me()
        _bot_username_cache = me.username
    return _bot_username_cache


PREMIUM_OFFER_TEXT = (
    "💎 <b>Premium подписка</b>\n\n"
    "Откройте все возможности AI English US для изучения английского.\n\n"
    "<b>Полный комплект для изучения:</b>\n"
    "<b>🎙️ Общение с AI</b> — искусственный интеллект почти неотличимый от живого носителя языка\n"
    "<b>🎬 Ролевые игры</b> — погружение в реальные жизненные сценарии без страха ошибиться\n"
    "<b>🔀 Грамматика</b> — отточите времена, конструкции и порядок слов на практике\n"
    "<b>🥇 Лексика</b> — вспоминайте и тренируйте слова по темам и уровням\n"
    "<b>📖 Чтение</b> — понимайте тексты любой сложности, от новостей до статей\n"
    "<b>🔉 Аудирование</b> — ловите интонации, акценты и смысл на слух\n"
    "<b>🗣️ Говорение</b> — свободно выражайте мысли без запинок и страха\n"
    "<b>📝 Письмо</b> — создавайте связные тексты с правильной структурой\n\n"
    "<b>Почему Premium — это выгодно:</b>\n"
    "<blockquote>"
    "• Занятия с репетитором стоят от 1500 ₽ за час.\n"
    "• Premium даёт вам неограниченную практику 24/7.\n"
    "• Вы занимаетесь в любое время без записи и привязки к расписанию.\n"
    "• ИИ-тьютор всегда на связи — отвечает мгновенно и объясняет ошибки.\n"
    "• За 30 дней вы получаете десятки часов практики по цене одного занятия с репетитором.\n"
    "</blockquote>\n"
    "<b>🤍 Никаких скрытых подписок. Вы платите только за те 30 дней, которые вам нужны.</b>"
)

PAYMENT_PANEL_TEXT = (
    "💳 <b>Оплата Premium-подписки</b>\n\n"
    f"Сумма: <b>{PRICE_RUB} ₽</b>\n"
    f"Срок: <b>{DURATION_DAYS} дней</b>\n\n"
    "Нажми <b>«Перейти к оплате»</b> — откроется страница ЮKassa.\n\n"
    "После оплаты вернись в бот и нажми <b>«Я оплатил(а) — проверить»</b>."
)

def get_offer_keyboard(from_profile: bool = False):
    buttons = [
        [InlineKeyboardButton(text=f"{DURATION_DAYS} дней — {PRICE_RUB} ₽", callback_data="subscribe_30_days")]
    ]
    if from_profile:
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_active_keyboard(from_profile: bool = False):
    if from_profile:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ])
    return None


def get_payment_keyboard(confirmation_url: str, from_profile: bool = False):
    buttons = [
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=confirmation_url)],
        [InlineKeyboardButton(text="🔄 Я оплатил(а) — проверить", callback_data="check_payment")],
    ]
    if from_profile:
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_subscription(target, user_id: int, from_profile: bool = False, edit: bool = False):
    profile = await get_user_profile(user_id)
    if not profile:
        if isinstance(target, CallbackQuery):
            await target.message.edit_text("Профиль не найден. Напишите /start для регистрации.")
        else:
            await target.answer("Профиль не найден. Напишите /start для регистрации.")
        return

    sub_end = profile.get("subscription_until", 0)
    now = int(datetime.now().timestamp())

    if sub_end and sub_end > now:
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        text = (
            f"✨ <b>Ваша подписка активна</b> ✨\n\n"
            f"<b>Действует до:</b> {expires}\n"
            f"<b>Тариф:</b> {PRICE_RUB} ₽ / {DURATION_DAYS} дней"
        )
        keyboard = get_active_keyboard(from_profile)
    else:
        text = PREMIUM_OFFER_TEXT
        keyboard = get_offer_keyboard(from_profile)

    if from_profile and edit and isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        if isinstance(target, CallbackQuery):
            await target.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def clear_active_mode(message: Message, state: FSMContext):
    """Чистит ЛЮБОЙ активный режим."""
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")

    if mode == "reading_active":
        data = await state.get_data()
        for key in ("last_task_msg_id", "progress_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(
                        chat_id=message.chat.id, message_id=msg_id, reply_markup=None
                    )
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.")
        return

    if mode == "speaking_active":
        speaking_kb_id = user_state.get("speaking_keyboard_msg_id")
        if speaking_kb_id:
            try:
                await message.bot.delete_message(message.chat.id, speaking_kb_id)
            except Exception:
                pass
            user_state.pop("speaking_keyboard_msg_id", None)
        user_state["mode"] = ""
        user_state["keyboard_hidden"] = True
        user_state["speaking_history"] = []
        user_state["russian_streak"] = 0
        user_state["pending_feedback"] = None
        user_state["feedback_prompt_msg_id"] = None
        set_user_state(user_id, user_state)
        await state.clear()
        msg = await message.answer("Переход...", reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(0.5)
        await msg.delete()
        return

    if mode == "roleplay_active":
        reply_kb_id = user_state.get("reply_keyboard_msg_id")
        if reply_kb_id:
            try:
                await message.bot.delete_message(message.chat.id, reply_kb_id)
            except Exception:
                pass
            user_state.pop("reply_keyboard_msg_id", None)
        user_state["mode"] = ""
        user_state["roleplay_history"] = []
        user_state["russian_counter"] = 0
        user_state.pop("roleplay_goal_notified", None)
        user_state.pop("roleplay_goal_ignored", None)
        user_state.pop("voice_id", None)
        set_user_state(user_id, user_state)
        await state.clear()
        msg = await message.answer("Переход...", reply_markup=ReplyKeyboardRemove())
        await asyncio.sleep(0.5)
        await msg.delete()
        return

    if mode == "grammar_active":
        data = await state.get_data()
        for key in ("task_msg_id", "progress_msg_id", "revision_msg_id", "revision_header_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=msg_id, reply_markup=None)
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "words_active":
        from handlers.words import user_message_ids, user_sessions, remove_buttons_from_messages
        if user_id in user_message_ids:
            msg_ids = list(user_message_ids[user_id].values())
            await remove_buttons_from_messages(message.bot, message.chat.id, msg_ids)
            user_message_ids[user_id] = {}
        user_sessions.pop(user_id, None)
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "listening_active":
        from handlers.listening import clear_user_buttons
        await clear_user_buttons(user_id, message.bot, message.chat.id)
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "writing_active":
        data = await state.get_data()
        for key in ("progress_msg_id", "last_task_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=msg_id, reply_markup=None)
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return

    if mode == "govorenie_active":
        data = await state.get_data()
        for key in ("progress_msg_id", "last_task_msg_id"):
            msg_id = data.get(key)
            if msg_id:
                try:
                    await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=msg_id, reply_markup=None)
                except Exception:
                    pass
        await state.clear()
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())
        return


@router.message(Command("subscription"))
async def subscription_command(message: Message, state: FSMContext):
    logger.info(f"✅ subscription_command вызван для {message.from_user.id}")
    await clear_active_mode(message, state)
    await show_subscription(message, message.from_user.id, from_profile=False, edit=False)


@router.callback_query(F.data == "subscribe_30_days")
async def handle_subscribe_30_days(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    user_id = callback.from_user.id
    profile = await get_user_profile(user_id)
    if not profile:
        await callback.message.edit_text("Профиль не найден. Напишите /start для регистрации.")
        return

    sub_end = profile.get("subscription_until", 0)
    now = int(datetime.now().timestamp())

    if sub_end and sub_end > now:
        await show_subscription(callback, user_id, from_profile=True, edit=True)
        return

    bot_username = await _get_bot_username(callback.bot)
    return_url = f"https://t.me/{bot_username}"

    payment = await create_payment(
        user_id=user_id,
        amount=PRICE_RUB,
        description=f"Premium подписка на {DURATION_DAYS} дней",
        return_url=return_url,
    )

    if not payment or not payment.get("confirmation_url"):
        await callback.message.edit_text(
            "Не удалось создать платёж. Попробуй ещё раз через минуту или обратись в поддержку.",
            reply_markup=None,
        )
        return

    await create_payment_record(
        payment_id=payment["payment_id"],
        user_id=user_id,
        amount=PRICE_RUB,
    )

    keyboard = get_payment_keyboard(payment["confirmation_url"], from_profile=True)
    try:
        await callback.message.edit_text(PAYMENT_PANEL_TEXT, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(PAYMENT_PANEL_TEXT, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "check_payment")
async def check_payment_handler(callback: CallbackQuery):
    try:
        await callback.answer("Проверяю...")
    except Exception:
        pass

    user_id = callback.from_user.id
    pending = await get_user_pending_payments(user_id)

    if not pending:
        await callback.message.answer(
            "Активных платежей не найдено. Если ты только что оплатил(а) — подожди 1–2 минуты и попробуй снова."
        )
        return

    payment_record = pending[0]
    payment_id = payment_record["payment_id"]

    yookassa_data = await get_payment_status(payment_id)
    if not yookassa_data:
        await callback.message.answer("Не удалось проверить статус. Попробуй позже.")
        return

    status = yookassa_data.get("status")

    if status == "succeeded":
        amount = float(yookassa_data.get("amount", {}).get("value", PRICE_RUB))
        ok = await activate_subscription_from_payment(payment_id, user_id, amount)
        if ok:
            await callback.message.answer(
                "<b>Оплата подтверждена!</b>\n\n"
                f"Подписка Premium активирована на {DURATION_DAYS} дней.\n"
                "Спасибо и приятного обучения! 💙",
                parse_mode="HTML",
            )
            await show_subscription(callback, user_id, from_profile=True, edit=False)
        else:
            await callback.message.answer(
                "Платёж прошёл, но не удалось активировать подписку. Напиши в поддержку — разберёмся."
            )
    elif status == "canceled":
        await callback.message.answer("Платёж отменён. Если это ошибка — попробуй создать новый.")
    elif status == "pending":
        await callback.message.answer(
            "⏳ Платёж ещё в обработке. Подожди 1–2 минуты и нажми «Я оплатил(а) — проверить» снова."
        )
    else:
        await callback.message.answer(f"Статус платежа: {status}. Попробуй позже.")


@router.callback_query(F.data == "back_to_profile")
async def back_to_profile_from_subscription(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
    from handlers.profile import profile_menu
    await profile_menu(callback)