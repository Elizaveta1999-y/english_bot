import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from datetime import datetime
from utils.db import get_user_profile
from data.users import get_user_state, set_user_state
import asyncio

logger = logging.getLogger(__name__)
router = Router()

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
    "• За месяц вы получаете десятки часов практики по цене одного занятия с репетитором.\n"
    "</blockquote>\n"
    "<b>🤍 Никаких скрытых подписок. Вы платите только за тот месяц, который вам нужен.</b>"
)

def get_offer_keyboard(from_profile: bool = False):
    buttons = [
        [InlineKeyboardButton(text="1 месяц — 999 ₽", callback_data="subscribe_30_days")]
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
            f"💳 <b>Ваша подписка активна</b>\n\n"
            f"<b>Действует до:</b> {expires}\n"
            f"<b>Тариф:</b> 999 ₽ / месяц\n\n"
            f"У вас есть доступ ко всем функциям Premium до указанной даты.\n"
            f"Продление не требуется — по окончании срока вы сможете оформить подписку снова, если захотите."
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

    await callback.message.edit_text(
        "💳 Оплата временно недоступна.\n\n"
        "Функция оплаты в разработке. Подписка будет активирована после завершения оплаты.\n"
        "Скоро мы добавим возможность оплаты через карту.",
        reply_markup=None,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_to_profile")
async def back_to_profile_from_subscription(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
    from handlers.profile import profile_menu
    await profile_menu(callback)