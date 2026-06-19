# handlers/subscription.py
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import get_user_state

router = Router()

@router.message(F.text == "/subscription")
async def show_subscription(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    sub = state.get("profile", {}).get("subscription", {})
    
    if sub.get("active"):
        expires = sub.get("expires", "не указана")
        text = (
            f"<b>Ваша подписка активна</b>\n\n"
            f"📅 Дата окончания: {expires}\n"
            f"Тариф: 900 ₽/мес\n\n"
            f"Чтобы продлить, нажмите кнопку ниже."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="profile_extend")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    else:
        text = (
            f"💳 <b>Подписка не активна</b>\n\n"
            f"Оформите подписку за 900 ₽/мес, чтобы получить:\n"
            f"• Неограниченный доступ к Language Skills\n"
            f"• Все уроки и практики\n"
            f"• Словарь с интервальным повторением\n"
            f"• Персональные рекомендации\n\n"
            f"Нажмите кнопку ниже, чтобы оплатить."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить подписку", callback_data="profile_extend")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")