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
        "🔗 <a href='https://disk.yandex.ru/docs/view?url=ya-disk%3A%2F%2F%2Fdisk%2FПубличная%20оферта%20(договор)%20об%20оказании%20информационных%20услуг%20с%20использованием%20ИИ%20для%20бота%20AI%20English%20US%20(2).pdf&name=Публичная%20оферта%20(договор)%20об%20оказании%20информационных%20услуг%20с%20использованием%20ИИ%20для%20бота%20AI%20English%20US%20(2).pdf&uid=1866726009&nosw=1'>Открыть соглашение</a>\n\n"
        "Используя бота, вы автоматически принимаете данные условия."
    )
    await message.answer(text, parse_mode="HTML")