from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import logging

from utils.db import get_user_profile, update_user_subscription

logger = logging.getLogger(__name__)
router = Router()

# ============================================================
# ТЕКСТ ДЛЯ НЕАКТИВНОЙ ПОДПИСКИ (ПРЕДЛОЖЕНИЕ)
# ============================================================
PREMIUM_OFFER_TEXT = (
    "💎 <b>Premium подписка</b>\n\n"
    "Откройте все возможности AI English US для изучения английского.\n\n"
    "<b>Полный комплект для изучения:</b>\n"
    "🎙️ Общение с AI — искусственный интеллект почти неотличимый от живого носителя языка\n"
    "🎬 Ролевые игры — погружение в реальные жизненные сценарии без страха ошибиться\n"
    "🔀 Грамматика — отточите времена, конструкции и порядок слов на практике\n"
    "🥇 Лексика — вспоминайте и тренируйте слова по темам и уровням\n"
    "📖 Чтение — понимайте тексты любой сложности, от новостей до статей\n"
    "🔉 Аудирование — ловите интонации, акценты и смысл на слух\n"
    "🗣️ Говорение — свободно выражайте мысли без запинок и страха\n"
    "📝 Письмо — создавайте связные тексты с правильной структурой\n\n"
    "<b>Почему Premium — это выгодно:</b>\n"
    "<blockquote>"
    "• Занятия с репетитором стоят от 1500 ₽ за час.\n"
    "• Premium даёт вам неограниченную практику 24/7.\n"
    "• Вы занимаетесь в любое время без записи и привязки к расписанию.\n"
    "• ИИ-тьютор всегда на связи — отвечает мгновенно и объясняет ошибки.\n"
    "• За месяц вы получаете десятки часов практики по цене одного занятия с репетитором.\n"
    "</blockquote>"
    "🤍 Никаких скрытых подписок. Вы платите только за тот месяц, который вам нужен."
)

def get_offer_keyboard(from_profile: bool = False):
    """Клавиатура для неактивной подписки."""
    buttons = [
        [InlineKeyboardButton(text="1 месяц — 999 ₽", callback_data="subscribe_30_days")]
    ]
    if from_profile:
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")])
    # Если from_profile=False — кнопки "Назад" нет вообще
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_active_keyboard(from_profile: bool = False):
    """Клавиатура для активной подписки."""
    if from_profile:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ])
    else:
        # Если из меню — кнопки "Назад" нет вообще
        return None

# ============================================================
# УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОКАЗА СТАТУСА ПОДПИСКИ
# ============================================================
async def show_subscription(message: Message, user_id: int, from_profile: bool = False):
    profile = await get_user_profile(user_id)
    if not profile:
        await message.answer("Профиль не найден. Напишите /start для регистрации.")
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
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        keyboard = get_offer_keyboard(from_profile)
        await message.answer(PREMIUM_OFFER_TEXT, reply_markup=keyboard, parse_mode="HTML")

# ============================================================
# ОБРАБОТЧИК КОМАНДЫ /subscription (без кнопки "Назад")
# ============================================================
@router.message(F.text == "/subscription")
async def subscription_command(message: Message):
    await show_subscription(message, message.from_user.id, from_profile=False)

# ============================================================
# ОБРАБОТЧИК КНОПКИ ОПЛАТЫ
# ============================================================
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
        await show_subscription(callback.message, user_id, from_profile=True)
        return

    new_sub_end = int((datetime.now() + timedelta(days=30)).timestamp())
    # await update_user_subscription(user_id, new_sub_end)

    logger.info(f"Пользователь {user_id} оформил подписку на 30 дней (тестовый режим)")

    await callback.message.edit_text(
        "💳 Оплата временно недоступна.\n\n"
        "Функция оплаты в разработке. Подписка будет активирована после завершения оплаты.\n"
        "Скоро мы добавим возможность оплаты через карту.",
        reply_markup=None,
        parse_mode="HTML"
    )

# ============================================================
# НАЗАД В ПРОФИЛЬ / СТАТИСТИКУ (из подписки, вызванной из профиля)
# ============================================================
@router.callback_query(F.data == "back_to_profile")
async def back_to_profile_from_subscription(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
    from handlers.profile import profile_menu
    await profile_menu(callback)