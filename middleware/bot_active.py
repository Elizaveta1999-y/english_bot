import logging
import os
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from utils.db import get_connection

logger = logging.getLogger(__name__)

TECH_MESSAGE = (
    "🛠️ <b>Небольшая пауза</b>\n\n"
    "Мы проводим технические работы, чтобы бот работал ещё лучше.\n"
    "Твои данные и прогресс в полной безопасности — ничего не потеряется.\n\n"
    "Пожалуйста, проверяй бота с небольшими паузами — скоро вернёмся 💙"
)

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))


class BotActiveMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        print(f">>> BotActive: {type(event).__name__} data={getattr(event, 'data', None)}", flush=True)

        user = data.get("event_from_user")
        if user and ADMIN_ID and user.id == ADMIN_ID:
            print(">>> BotActive: админ, пропускаем", flush=True)
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

        if val == 'true':
            print(">>> BotActive: бот активен, пропускаем", flush=True)
            return await handler(event, data)

        print(">>> BotActive: бот НЕ активен, показываем техработы", flush=True)
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