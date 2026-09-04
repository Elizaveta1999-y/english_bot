import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()

# Добавим лог при регистрации роутера (сработает при импорте)
logger.info("✅ Роутер agreement загружен")

@router.message(Command("agreement"))
async def agreement_command(message: Message):
    logger.info(f"🔥 Получена команда /agreement от {message.from_user.id}")
    text = (
        "<b>Пользовательское соглашение</b>\n\n"
        "Ознакомьтесь с условиями использования бота.\n"
        "Полный текст доступен по ссылке:\n"
        "🔗 <a href='https://disk.yandex.ru/ВАША_КОРОТКАЯ_ССЫЛКА'>Открыть соглашение</a>\n\n"
        "Используя бота, вы автоматически принимаете данные условия."
    )
    await message.answer(text, parse_mode="HTML")
    logger.info("✅ Сообщение отправлено")