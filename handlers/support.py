import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("support"))
async def support_start(message: Message):
    logger.info(f"✅ support_start вызван для {message.from_user.id}")
    user_id = message.from_user.id
    text = (
        "Вам нужна помощь или имеются вопросы?\n"
        "Поддержка бота - support.english.bot@gmail.com\n\n"
        f"🆔 <b>Ваш ID аккаунта:</b> <code>{user_id}</code>\n\n"
        "Подробно опишите вашу ситуацию и по возможности, приложите скриншоты.\n"
        "Свяжемся с вами как можно скорее!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")