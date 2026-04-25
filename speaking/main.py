import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start_router)
dp.include_router(voice_router)

async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())