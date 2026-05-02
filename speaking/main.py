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

# Временный обработчик сообщений
@dp.message()
async def echo(message: types.Message):
    await message.answer("I received your message! Bot is working.")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = None

def get_webhook_url():
    # Пробуем получить внешний URL несколькими способами
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        return f"{external_url}{WEBHOOK_PATH}"
    # Fallback: используем имя сервиса
    service_name = os.environ.get("RENDER_SERVICE_NAME", "localhost")
    return f"https://{service_name}.onrender.com{WEBHOOK_PATH}"

@app.route(WEBHOOK_PATH, methods=['POST'])
async def webhook():
    try:
        data = request.get_json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
        return "OK", 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return "Error", 500

@app.route("/")
def index():
    return "Bot is running!", 200

# Устанавливаем вебхук при запуске (через отдельную функцию, чтобы избежать конфликта циклов событий)
def setup_webhook():
    global WEBHOOK_URL
    WEBHOOK_URL = get_webhook_url()
    # Создаём новый event loop для синхронного вызова
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.set_webhook(WEBHOOK_URL))
        logging.info(f"Webhook set to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")
    finally:
        loop.close()

# Используем более современный способ для Flask 3.0
with app.app_context():
    setup_webhook()