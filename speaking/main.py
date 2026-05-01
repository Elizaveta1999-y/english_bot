import asyncio
import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = None

async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def health_check(request):
    return web.Response(text="OK")

async def on_startup(app):
    global WEBHOOK_URL
    port = int(os.environ.get("PORT", 10000))
    # Render предоставляет внешний URL
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not external_url:
        external_url = f"https://{os.environ.get('RENDER_SERVICE_NAME', 'localhost')}.onrender.com"
    WEBHOOK_URL = f"{external_url}{WEBHOOK_PATH}"
    
    # Удаляем старый вебхук и устанавливаем новый
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("Webhook removed")

def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"Starting web server on port {port}")
    web.run_app(app, host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()