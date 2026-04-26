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

async def handle_health_check(request):
    return web.Response(text="Bot is running")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health check server started on port {port}")
    # Keep the server running indefinitely
    await asyncio.Event().wait()

async def main():
    # Запускаем веб-сервер как отдельную задачу, но не ждём её
    asyncio.create_task(run_web_server())
    # Небольшая задержка, чтобы сервер успел запуститься
    await asyncio.sleep(1)
    # Устанавливаем команды бота
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    # Запускаем polling — это основной процесс, который будет работать постоянно
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())