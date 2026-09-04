from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("agreement"))
async def agreement_command(message: Message):
    text = (
        "<b>Пользовательское соглашение и другие документы</b>\n\n"
        "Все официальные документы доступны в одной папке:\n"
        "🔗 <a href='https://disk.yandex.ru/d/b0CooYtb5OxXgQ'>Открыть папку с документами</a>\n\n"
        "Ознакомьтесь с условиями использования, политикой конфиденциальности и тарифами."
    )
    await message.answer(text, parse_mode="HTML")