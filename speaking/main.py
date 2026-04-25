import asyncio
import os
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

# === ФЕЙКОВЫЙ СЕРВЕР ДЛЯ RENDER ====
async def handle(request):
    return web.Response(text="Bot is running")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# === ЗАПУСК ====
async def main():
    await start_web_server()
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())