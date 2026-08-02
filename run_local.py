import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from handlers import (
    start, speaking, roleplay, common, voice, lessons, words,
    profile, support, listening, reading, writing
)
from handlers.grammar import router as grammar_router
from handlers.govorenie import router as govorenie_router
from utils.db import init_db

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== MIDDLEWARE ДЛЯ ОГРАНИЧЕНИЯ ДОСТУПА ==========
YOUR_USER_ID = 6115540828  # ваш Telegram ID

class AdminOnlyMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Проверяем, есть ли у события пользователь
        user = None
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user
        if user and user.id != YOUR_USER_ID:
            # Если это не вы — отвечаем и прерываем обработку
            if isinstance(event, Message):
                await event.answer("🚫 Это тестовый бот, доступ ограничен.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Доступ запрещён.", show_alert=True)
            return  # не передаём дальше
        return await handler(event, data)

# Регистрируем middleware для всех типов событий
dp.message.middleware(AdminOnlyMiddleware())
dp.callback_query.middleware(AdminOnlyMiddleware())

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
    print("🚀 Бот запущен локально (тестовый режим, доступ только для вас)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())