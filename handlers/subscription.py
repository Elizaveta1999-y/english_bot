from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import logging

from utils.db import get_user_profile, update_user_subscription
from data.users import get_user_state, set_user_state
from handlers.start import show_main_menu

logger = logging.getLogger(__name__)
router = Router()

# ============================================================
# ТЕКСТ ДЛЯ НЕАКТИВНОЙ ПОДПИСКИ (ПРЕДЛОЖЕНИЕ)
# ============================================================
PREMIUM_OFFER_TEXT = (
    "💎 <b>Premium подписка</b>\n\n"
    "Откройте все возможности AI English US для изучения английского.\n\n"
    "<b>Что вы получаете:</b>\n\n"
    "🎙️ <b>Общение с AI</b> — диалог как с живым человеком\n"
    "🔀 <b>Грамматика</b> — все правила с практикой\n"
    "🥇 <b>Лексика</b> — слова и выражения по категориям\n"
    "🔉 <b>Аудирование</b> — тренировка восприятия на слух\n"
    "📝 <b>Письмо</b> — задания с детальной проверкой ИИ\n"
    "🗣️ <b>Говорение</b> — практика произношения с оценкой\n"
    "🎬 <b>Ролевые игры</b> — живая практика в реальных ситуациях\n"
    "📊 <b>Детальная статистика прогресса</b>\n\n"
    "<b>Почему Premium — это выгодно:</b>\n"
    "<blockquote>"
    "• Занятия с репетитором стоят от 1500 ₽ за час.\n"
    "• Premium даёт вам неограниченную практику 24/7.\n"
    "• Вы занимаетесь в любое время без записи и привязки к расписанию.\n"
    "• ИИ-тьютор всегда на связи — отвечает мгновенно и объясняет ошибки.\n"
    "• За месяц вы получаете десятки часов практики по цене одного занятия с репетитором.\n"
    "</blockquote>\n"
    "🤍 Никаких скрытых подписок. Деньги не списываются автоматически — вы платите только за тот месяц, который вам нужен.\n\n"
    "💰 30 дней — всего 999 ₽"
)

# ============================================================
# КЛАВИАТУРЫ
# ============================================================
def get_offer_keyboard():
    """Клавиатура для предложения подписки (неактивна)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Оплатить 999 ₽", callback_data="subscribe_30_days")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_active_keyboard():
    """Клавиатура для активной подписки (только Назад)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================
@router.message(F.text == "/subscription")
async def show_subscription_command(message: Message):
    """Обработчик команды /subscription"""
    user_id = message.from_user.id
    await show_subscription(message, user_id)

async def show_subscription(message: Message, user_id: int):
    """Общая функция для отображения статуса подписки"""
    profile = await get_user_profile(user_id)
    if not profile:
        await message.answer("Профиль не найден. Напишите /start для регистрации.")
        return

    sub_end = profile.get("subscription_until", 0)
    now = int(datetime.now().timestamp())

    if sub_end and sub_end > now:
        # ===== ПОДПИСКА АКТИВНА =====
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        text = (
            f"💳 <b>Ваша подписка активна</b>\n\n"
            f"<b>Действует до:</b> {expires}\n"
            f"<b>Тариф:</b> 999 ₽ / месяц\n\n"
            f"У вас есть доступ ко всем функциям Premium до указанной даты.\n"
            f"Продление не требуется — по окончании срока вы сможете оформить подписку снова, если захотите."
        )
        await message.answer(text, reply_markup=get_active_keyboard(), parse_mode="HTML")
    else:
        # ===== ПОДПИСКА НЕ АКТИВНА =====
        await message.answer(PREMIUM_OFFER_TEXT, reply_markup=get_offer_keyboard(), parse_mode="HTML")

# ============================================================
# ОБРАБОТЧИК НАЖАТИЯ КНОПКИ ОПЛАТЫ
# ============================================================
@router.callback_query(F.data == "subscribe_30_days")
async def handle_subscribe_30_days(callback: CallbackQuery):
    """Обработчик оплаты на 30 дней"""
    try:
        await callback.answer()
    except Exception:
        pass

    user_id = callback.from_user.id

    # Проверяем, не активна ли уже подписка
    profile = await get_user_profile(user_id)
    if not profile:
        await callback.message.edit_text("Профиль не найден. Напишите /start для регистрации.")
        return

    sub_end = profile.get("subscription_until", 0)
    now = int(datetime.now().timestamp())

    if sub_end and sub_end > now:
        # Если подписка уже активна, показываем статус
        await show_subscription(callback.message, user_id)
        return

    # ===== ЗДЕСЬ БУДЕТ ЛОГИКА ОПЛАТЫ (ПОКА ЗАГЛУШКА) =====
    # Когда подключишь платежи, здесь будет:
    # - Создание счета
    # - Перенаправление на оплату
    # - Ожидание подтверждения

    # ВРЕМЕННО: просто активируем подписку на 30 дней (для теста)
    new_sub_end = int((datetime.now() + timedelta(days=30)).timestamp())
    # Обновляем подписку в БД (нужно добавить функцию в db.py)
    # await update_user_subscription(user_id, new_sub_end)

    logger.info(f"Пользователь {user_id} оформил подписку на 30 дней (тестовый режим)")

    # Показываем сообщение о том, что оплата будет позже
    await callback.message.edit_text(
        "💳 Оплата временно недоступна.\n\n"
        "Функция оплаты в разработке. Подписка будет активирована после завершения оплаты.\n"
        "Скоро мы добавим возможность оплаты через карту.",
        reply_markup=get_active_keyboard(),
        parse_mode="HTML"
    )

# ============================================================
# НАЗАД В ГЛАВНОЕ МЕНЮ
# ============================================================
@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_subscription(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass
    await show_main_menu(callback.message, edit=True)

# ============================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОБНОВЛЕНИЯ ПОДПИСКИ (ВРЕМЕННО)
# ============================================================
# Позже добавим в utils/db.py:
# async def update_user_subscription(user_id: int, new_end: int):
#     conn = await get_connection()
#     await conn.execute(
#         "UPDATE users SET subscription_until = $1 WHERE user_id = $2",
#         new_end, user_id
#     )
#     await conn.close()