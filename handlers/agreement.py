from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("agreement"))
async def agreement_command(message: Message):
    text = (
        "<b>Пользовательское соглашение</b>\n\n"
        "Ознакомьтесь с условиями использования бота.\n"
        "Полный текст доступен по ссылке:\n"
        "🔗 <a href='https://disk.yandex.ru/edit/d/4NDocdmWhHkDNQ_MTl78rCPegnqahzm72s0qoIz-cKg6Yl9hVHk5NWhGUQ?source=docs'>Открыть соглашение</a>\n\n"
        "Используя бота, вы автоматически принимаете данные условия."
    )
    await message.answer(text, parse_mode="HTML")