import logging
import os
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from utils.db import get_connection

logger = logging.getLogger(__name__)

TECH_MESSAGE = (
    "🛠️ Небольшая пауза\n\n"
    "Мы проводим технические работы, чтобы бот работал ещё лучше.\n"
    "Твои данные и прогресс в полной безопасности — ничего не потеряется.\n\n"
    "Скоро вернёмся! 💙"
)

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))


class BotActiveMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Пропускаем админа — он может тестировать
        user = data.get("event_from_user")
        if user and ADMIN_ID and user.id == ADMIN_ID:
            return await handler(event, data)

        # Читаем флаг из БД
        try:
            conn = await get_connection()
            try:
                val = await conn.fetchval(
                    "SELECT value FROM bot_settings WHERE key = 'is_active'"
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"BotActiveMiddleware: ошибка чтения флага: {e}")
            # если не смогли прочитать — пропускаем, чтобы не блокировать всё
            return await handler(event, data)

        if val == 'true':
            return await handler(event, data)

        # Бот на техработах
        if isinstance(event, Message):
            try:
                await event.answer(TECH_MESSAGE)
            except Exception:
                pass
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(TECH_MESSAGE, show_alert=True)
            except Exception:
                pass
        return