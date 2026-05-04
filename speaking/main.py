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

WEBHOOK_PATH = "/webhook"

# Временное хранилище для пользователей
users = {}

# ========== ОБРАБОТЧИКИ (синхронные) ==========

@dp.message(Command("start"))
async def start_command(message: types.Message):
    logger.info(f"User {message.from_user.id} started the bot")
    await message.answer(
        "Hello! 🤖\n\n"
        "I'm your personal English tutor.\n"
        "Send me a voice message to practice English!"
    )

# Временный echo для всех сообщений
@dp.message()
async def echo_all(message: types.Message):
    logger.info(f"Received: {message.text if message.text else 'voice'}")
    await message.answer("Bot is working! Send me a voice message 📢")

# ========== ВЕБХУК (синхронная обработка) ==========

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = Update(**data)
        
        # Обрабатываем update синхронно через event loop
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(dp.feed_update(bot, update))
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

@app.route('/')
def index():
    return "Bot is running!", 200

# Установка вебхука
logger.info("Setting webhook...")
external_url = "https://english-bot-d1pd.onrender.com"
webhook_url = f"{external_url}{WEBHOOK_PATH}"

response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    json={"url": webhook_url, "drop_pending_updates": True}
)
logger.info(f"Webhook response: {response.json()}")