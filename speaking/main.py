import os
import logging
import asyncio
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    logger.info(f"User {message.from_user.id} started the bot")
    await message.answer(
        "Hello! 🤖\n\n"
        "I'm your personal English tutor.\n"
        "Send me a voice message to practice English!"
    )

# Обработчик текстовых сообщений (для эха)
@dp.message()
async def echo(message: types.Message):
    logger.info(f"Received text: {message.text}")
    await message.answer(f"You said: {message.text}")

# Обработчик голосовых сообщений
@dp.message(lambda m: m.voice)
async def handle_voice(message: types.Message):
    logger.info(f"Received voice message from {message.from_user.id}")
    await message.answer("I received your voice message! Processing...")

# Вебхук эндпоинт
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = Update(**data)
        asyncio.run(dp.feed_update(bot, update))
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

@app.route('/')
def index():
    return "Bot is running!", 200

logger.info("Bot is ready")