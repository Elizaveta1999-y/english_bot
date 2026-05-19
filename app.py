import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"  # можно заменить на любой секрет

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

async def on_startup(app: web.Application):
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"  # замените на ваш URL
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    logging.info(f"Webhook set to {webhook_url}")

dp.startup.register(on_startup)

app = web.Application()
webhook_requests_handler = SimpleRequestHandler(
    dispatcher=dp,
    bot=bot,
    secret_token=WEBHOOK_SECRET,
)
webhook_requests_handler.register(app, path=WEBHOOK_PATH)

setup_application(app, dp, bot=bot)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    web.run_app(app, host='0.0.0.0', port=port)