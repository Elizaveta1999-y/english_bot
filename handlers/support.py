# handlers/support.py (для основного бота)
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# ID администратора (ваш ID) — для пересылки сообщений из бота поддержки
# Этот ID не будет виден пользователям, он используется только в боте поддержки
ADMIN_ID = 123456789  # замените на ваш реальный ID

@router.message(F.text == "/support")
async def support_start(message: Message):
    user_id = message.from_user.id
    # Формируем сообщение с контактом поддержки и ID пользователя
    text = (
        "📞 <b>Поддержка</b>\n\n"
        "Вам нужна помощь или имеются вопросы?\n"
        "Поддержка бота — @AI_English_Support_bot\n\n"
        f"🆔 <b>Ваш ID аккаунта:</b> <code>{user_id}</code>\n\n"
        "Перейдите в бот поддержки, нажмите /start и опишите вашу проблему."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Перейти в поддержку", url="https://t.me/AI_English_Support_bot")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")