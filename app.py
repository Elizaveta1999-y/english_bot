import os
import logging
from flask import Flask, request
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

app = Flask(__name__)

WEBHOOK_PATH = "/webhook"

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = Update(**data)
        # Запускаем асинхронную обработку в синхронном контексте
        import asyncio
        asyncio.run(dp.feed_update(bot, update))
        return "OK", 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return "Error", 500

@app.route("/")
def index():
    return "Bot is running", 200

# Установка вебхука при старте (выполнится один раз)
def set_webhook():
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_URL', 'english-bot-wdfa.onrender.com')}{WEBHOOK_PATH}"
    try:
        import asyncio
        asyncio.run(bot.set_webhook(webhook_url))
        logging.info(f"Webhook set to {webhook_url}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")

set_webhook()