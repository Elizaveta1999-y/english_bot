import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

from handlers.start import start

TOKEN = "8652892060:AAGnlfueIW4WVenereDZjRjV3E0dOuHu8vg"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await start(message)

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())