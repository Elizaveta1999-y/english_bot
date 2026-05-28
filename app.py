import os
import logging
import asyncio
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

WEBHOOK_PATH = "/webhook"

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Привет! Бот работает через вебхук. Отправь любое сообщение.")

@dp.message()
async def echo(message: types.Message):
    await message.answer(f"Вы сказали: {message.text}")

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = Update(**data)
        # Запускаем асинхронную обработку в синхронном контексте
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
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    try:
        asyncio.run(bot.set_webhook(webhook_url))
        logging.info(f"Webhook set to {webhook_url}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")

set_webhook()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)