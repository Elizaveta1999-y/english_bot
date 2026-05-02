import os
import logging
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# Временный обработчик сообщений
@dp.message()
async def echo(message: types.Message):
    await message.answer("I received your message! Bot is working.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = None

@app.route(WEBHOOK_PATH, methods=['POST'])
async def webhook():
    try:
        update = types.Update(**request.get_json())
        await dp.feed_update(bot, update)
        return "OK", 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return "Error", 500

@app.route("/")
def index():
    return "Bot is running!", 200

# Устанавливаем вебхук при старте приложения
with app.app_context():
    import asyncio
    WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_URL')}{WEBHOOK_PATH}"
    asyncio.run(bot.set_webhook(WEBHOOK_URL))
    logging.info(f"Webhook set to {WEBHOOK_URL}")