import asyncio
from aiogram import Bot, Dispatcher

from handlers.start import router as start_router
from handlers.voice import router as voice_router

BOT_TOKEN = "8652892060:AAGnlfueIW4WVenereDZjRjV3E0dOuHu8vg"


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем ВСЕ роутеры
    dp.include_router(start_router)
    dp.include_router(voice_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())