import asyncio
import os
import threading
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiohttp import web
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

# Простой фиктивный веб-сервер для health checks
async def health_check(request):
    return web.Response(text="OK")

def run_web_server():
    """Запускает веб-сервер в отдельном потоке."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host='0.0.0.0', port=port)

async def main():
    # Запускаем веб-сервер в отдельном потоке, чтобы не блокировать asyncio
    thread = threading.Thread(target=run_web_server, daemon=True)
    thread.start()
    
    # Даем серверу время запуститься
    await asyncio.sleep(1)
    
    # Устанавливаем команды бота
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    
    # Запускаем polling (основная работа бота)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())