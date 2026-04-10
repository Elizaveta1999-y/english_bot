import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from handlers.start import start, handle_buttons
from handlers.voice import handle_voice

TOKEN = "8652892060:AAGnlfueIW4WVenereDZjRjV3E0dOuHu8vg"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# команды
dp.message.register(start, Command("start"))

# кнопки
dp.callback_query.register(handle_buttons)

# голос
dp.message.register(handle_voice)


async def main():
    print("Бот запущен 🚀")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())