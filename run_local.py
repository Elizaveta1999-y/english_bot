import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher
from handlers import start, speaking, roleplay, common, voice, lessons, words, profile, support, listening, reading, writing
from handlers.grammar import router as grammar_router
from handlers.govorenie import router as govorenie_router
from utils.db import init_db

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(words.router)
dp.include_router(govorenie_router)
dp.include_router(writing.router)
dp.include_router(reading.router)
dp.include_router(listening.router)
dp.include_router(grammar_router)
dp.include_router(support.router)
dp.include_router(roleplay.router)
dp.include_router(voice.router)
dp.include_router(common.router)
dp.include_router(lessons.router)
dp.include_router(speaking.router)
dp.include_router(profile.router)

async def main():
    await init_db()
    print("🚀 Бот запущен локально")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())