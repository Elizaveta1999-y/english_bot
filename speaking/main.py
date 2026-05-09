import os
import logging
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.filters import Command

# Импорт ваших роутеров (они должны быть, но для диагностики добавим прямой обработчик)
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

# Прямой обработчик команды /start (для диагностики)
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    logger.info(f"Start command received from {message.from_user.id}")
    await message.answer("Hello! Bot is working. Send me a voice message to practice English.")

# Подключаем ваши роутеры (они могут переопределить, если есть дубликаты)
dp.include_router(start_router)
dp.include_router(voice_router)

WEBHOOK_PATH = "/webhook"

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = Update(**data)
        import asyncio
        # Получаем или создаём event loop
        try:
            loop = asyncio.get_running_loop()
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
import requests
response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    json={"url": webhook_url, "drop_pending_updates": True}
)
logger.info(f"Webhook response: {response.json()}")