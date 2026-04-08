import asyncio
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Берем токен из Render (Environment Variables)
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()


# Команда /start
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Привет! Бот работает 🚀")


# Любое сообщение
@dp.message()
async def echo(message: types.Message):
    await message.answer(f"Ты написал: {message.text}")


# Запуск бота
async def main():
    print("Бот запущен ✅")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())