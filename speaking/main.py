import os
import logging
import asyncio
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# Синхронный обработчик для вебхука
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = types.Update(**data)
        # Запускаем асинхронную функцию в синхронном контексте
        asyncio.run(process_update(update))
        return "OK", 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return "Error", 500

async def process_update(update):
    await dp.feed_update(bot, update)

@app.route('/')
def index():
    return "Bot is running!", 200

# Простой echo-обработчик
@dp.message()
async def echo(message: types.Message):
    await message.answer("I received your message! Bot is working.")

# Устанавливаем вебхук
def setup_webhook():
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not external_url:
        external_url = "https://english-bot.onrender.com"  # замените на ваш реальный URL
    webhook_url = f"{external_url}/webhook"
    
    # Удаляем старый вебхук и устанавливаем новый
    try:
        asyncio.run(bot.delete_webhook())
        asyncio.run(bot.set_webhook(webhook_url))
        logging.info(f"Webhook set to {webhook_url}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")

# Запускаем установку вебхука при старте
setup_webhook()