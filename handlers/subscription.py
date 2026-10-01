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
    get_user_tariff_async,
)
from services.yookassa import create_payment, get_payment_status
from data.users import get_user_state, set_user_state
import asyncio

logger = logging.getLogger(__name__)
router = Router()

DURATION_DAYS = 30

TARIFFS = {
    "light": {
        "price": 490,
        "label": "Лайт",
        "description": "лёгкая голосовая практика",
    },
    "base": {
        "price": 999,
        "label": "Про",
        "description": "интенсивный темп",
    },
}

_bot_username_cache = None

async def _get_bot_username(bot):
    global _bot_username_cache
    if _bot_username_cache is None:
        me = await bot.get_me()
        _bot_username_cache = me.username
    return _bot_username_cache


PREMIUM_OFFER_TEXT = (
    "💎 <b>Premium подписка</b>\n\n"
    "Каждая попытка заговорить — с разбором.\n\n"
    "🗣️ <b>Говорение</b> — AI слушает и разбирает речь: где ошибка, как правильно и почему\n"
    "📝 <b>Письмо</b> — email, эссе, посты, истории. Проверка структуры, грамматики, стиля\n"
    "🎬 <b>Ролевые игры</b> — путешествия, small talk, неожиданные ситуации\n"
    "🎙️ <b>Общение с AI</b> — говорите голосом. AI моментально объясняет каждую ошибку\n\n"
    "Оба тарифа включают <b>всё это</b>. Разница в объеме голоса. Минуты общие на общение с AI и на ролевые игры (то есть тратите, куда хотите):\n"
    "• ☕️ <b>Лайт</b> — 30 минут в месяц\n"
    "• 🏋🏻‍♂️ <b>Про</b> — 2.5 часа в месяц\n\n"
    "Первые 48 часов — бесплатно.\n\n"
    "<b>Почему выгодно:</b>\n"
    "<blockquote>• Репетитор — от 1500 ₽ за час\n"
    "• Здесь вы платите за 30 дней, а не за 60 минут\n"
    "• Без автопродления и скрытых списаний 🤍</blockquote>"
)


def _tariff_label(tariff_key: str) -> str:
    return TARIFFS.get(tariff_key, {}).get("label", "Premium")


def get_payment_panel_text(tariff_key: str) -> str:
    t = TARIFFS[tariff_key]
    return (
        "💳 <b>Оплата Premium-подписки</b>\n\n"
        f"Тариф: <b>{t['label']}</b>\n"
        f"Сумма: <b>{t['price']} ₽</b>\n"
        f"Срок: <b>{DURATION_DAYS} дней</b>\n\n"
        "После оплаты вернись в бот и нажми <b>«Я оплатил(а) — проверить»</b>."
    )


def get_offer_keyboard(from_profile: bool = False):
    buttons = [
        [InlineKeyboardButton(
            text=f"Лайт — {TARIFFS['light']['price']} ₽",
            callback_data="subscribe_light"
        )],
        [InlineKeyboardButton(
            text=f"Про — {TARIFFS['base']['price']} ₽",
            callback_data="subscribe_base"
        )],
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
        tariff_key = profile.get("tariff") or "base"
        tariff_label = _tariff_label(tariff_key)
        text = (
            f"✨ <b>Ваша подписка активна</b> ✨\n\n"
            f"<b>Тариф:</b> {tariff_label}\n"
            f"<b>Действует до:</b> {expires}"
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


async def _start_payment(callback: CallbackQuery, tariff_key: str):
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

    tariff = TARIFFS[tariff_key]
    bot_username = await _get_bot_username(callback.bot)
    return_url = f"https://t.me/{bot_username}"

    payment = await create_payment(
        user_id=user_id,
        amount=tariff["price"],
        description=f"Premium подписка ({tariff['label']}) на {DURATION_DAYS} дней",
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
        amount=tariff["price"],
        tariff=tariff_key,
    )

    panel_text = get_payment_panel_text(tariff_key)
    keyboard = get_payment_keyboard(payment["confirmation_url"], from_profile=True)
    try:
        await callback.message.edit_text(panel_text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(panel_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "subscribe_light")
async def handle_subscribe_light(callback: CallbackQuery):
    await _start_payment(callback, "light")


@router.callback_query(F.data == "subscribe_base")
async def handle_subscribe_base(callback: CallbackQuery):
    await _start_payment(callback, "base")


@router.callback_query(F.data == "check_payment")
async def check_payment_handler(callback: CallbackQuery):
    try:
        await callback.answer("Проверяю...")
    except Exception:
        pass

    user_id = callback.from_user.id

    profile = await get_user_profile(user_id)
    now = int(datetime.now().timestamp())
    sub_end = (profile or {}).get("subscription_until", 0)
    if sub_end and sub_end > now:
        tariff_key = (profile or {}).get("tariff") or "base"
        tariff_label = _tariff_label(tariff_key)
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        await callback.message.answer(
            f"✅ <b>Оплата уже подтверждена!</b>\n\n"
            f"Тариф: <b>{tariff_label}</b>\n"
            f"Подписка активна до <b>{expires}</b>.\n\n"
            "Спасибо и приятного обучения! 💙",
            parse_mode="HTML",
        )
        await show_subscription(callback, user_id, from_profile=True, edit=False)
        return

    pending = await get_user_pending_payments(user_id)

    if not pending:
        await callback.message.answer(
            "Не нашли активный платёж. Если ты только что оплатил(а) — подожди 1–2 минуты и попробуй снова. "
            "Если деньги списались, а подписка не активировалась — напиши в поддержку."
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
        amount = float(yookassa_data.get("amount", {}).get("value", 0))
        ok = await activate_subscription_from_payment(payment_id, user_id, amount)
        if ok:
            tariff_key = await get_user_tariff_async(user_id)
            tariff_label = _tariff_label(tariff_key) if tariff_key else "Premium"
            await callback.message.answer(
                "<b>Оплата подтверждена!</b>\n\n"
                f"Тариф: <b>{tariff_label}</b>\n"
                f"Подписка активна на {DURATION_DAYS} дней.\n"
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


@router.callback_query(F.data == "show_tariffs")
async def show_tariffs_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await clear_active_mode(callback.message, state)
    await show_subscription(callback, callback.from_user.id, from_profile=False, edit=False)