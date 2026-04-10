from aiogram.types import Message

async def start(message: Message):
    await message.answer("Привет! 👋 Бот работает на aiogram 🚀")