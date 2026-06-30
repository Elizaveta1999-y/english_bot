import os
from aiogram import BaseMiddleware
from aiogram.types import Message

class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        mode = os.getenv("BOT_ACCESS_MODE", "open")
        if mode == "restricted":
            allowed = [int(x.strip()) for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip()]
            user_id = event.from_user.id
            if user_id not in allowed:
                await event.answer(
                    "🔐 Бот временно находится в режиме технического обслуживания.\n"
                    "Мы скоро откроем доступ для всех 🚀"
                )
                return  # прерываем обработку
        return await handler(event, data)