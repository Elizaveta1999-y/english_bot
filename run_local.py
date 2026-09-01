import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher
from handlers import (
    start, speaking, roleplay, common, voice, lessons, words,
    profile, support, listening, reading, writing
)
from handlers.grammar import router as grammar_router
from handlers.govorenie import router as govorenie_router
from utils.db import init_db
from middleware.speaking_override import SpeakingOverrideMiddleware

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== РЕГИСТРАЦИЯ MIDDLEWARE ==========
# ВСЕ СТАРЫЕ MIDDLEWARE ЗАКОММЕНТИРОВАНЫ – ОСТАВЛЕН ТОЛЬКО НАШ

# dp.message.middleware(AdminOnlyMiddleware())           # закомментировано
# dp.callback_query.middleware(AdminOnlyMiddleware())    # закомментировано
# dp.message.middleware(ModeIsolationMiddleware())       # закомментировано
# dp.message.middleware(close_speaking_on_exit)          # закомментировано
# dp.callback_query.middleware(close_speaking_on_exit)   # закомментировано

# ОСТАВЛЯЕМ ТОЛЬКО НАШ
dp.message.middleware(SpeakingOverrideMiddleware())
dp.callback_query.middleware(SpeakingOverrideMiddleware())

# ========== ПОДКЛЮЧАЕМ РОУТЕРЫ ==========
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
    print("🚀 Бот запущен локально (тестовый режим)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())