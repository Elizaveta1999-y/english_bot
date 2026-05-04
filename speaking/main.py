import os
import logging
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.filters import Command
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# Простой путь для вебхука (без переменных частей)
WEBHOOK_PATH = "/webhook"

@dp.message(Command("start"))
async def start_command(message: types.Message):
    logger.info(f"User {message.from_user.id} started the bot")
    await message.answer(
        "Hello! 🤖\n\n"
        "I'm your personal English tutor.\n"
        "Send me a voice message to practice English!"
    )

@dp.message()
async def echo(message: types.Message):
    logger.info(f"Received text: {message.text}")
    await message.answer(f"You said: {message.text}")

@dp.message(lambda m: m.voice)
async def handle_voice(message: types.Message):
    logger.info(f"Received voice from {message.from_user.id}")
    await message.answer("I received your voice message! Processing...")

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = Update(**data)
        import asyncio
        asyncio.run(dp.feed_update(bot, update))
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

@app.route('/')
def index():
    return "Bot is running!", 200

# Устанавливаем вебхук при запуске
logger.info(f"Setting webhook on {WEBHOOK_PATH}...")
external_url = "https://english-bot-d1pd.onrender.com"
webhook_url = f"{external_url}{WEBHOOK_PATH}"
logger.info(f"Webhook URL: {webhook_url}")

response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    json={"url": webhook_url, "drop_pending_updates": True}
)
logger.info(f"Webhook response: {response.json()}")