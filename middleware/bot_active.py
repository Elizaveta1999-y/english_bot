import logging
import os
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from utils.db import get_connection

logger = logging.getLogger(__name__)

TECH_MESSAGE = (
    "🤍 <b>Айва уходит на доработку</b>\n\n"
    "Мы на месяц закрываем бота, чтобы сделать Айву такой, какой задумывали: "
    "наставником, который помнит твои ошибки, ведёт тебя по плану и доводит до цели — "
    "а не просто отвечает на сообщения.\n\n"
    "До 17.11.26 пришлём уведомление, как только вернёмся.\n\n"
    "Спасибо, что ты с нами. Это только начало 🤍"
)

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))


class BotActiveMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")

        # Админа всегда пропускаем
        if user and ADMIN_ID and user.id == ADMIN_ID:
            return await handler(event, data)

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
            return await handler(event, data)

        # Если бот активен — пропускаем
        if val == 'true':
            return await handler(event, data)

        # Если бот выключен — показываем текст про техработы
        if isinstance(event, Message):
            try:
                await event.answer(TECH_MESSAGE, parse_mode="HTML")
            except Exception:
                pass
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(TECH_MESSAGE, show_alert=True, parse_mode="HTML")
            except Exception:
                pass
        return