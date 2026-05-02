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

# Временно — простой ответ на любое сообщение
@dp.message()
async def echo(message: types.Message):
    await message.answer("I received your message! Bot is working.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.environ.get('RENDER_EXTERNAL_URL')}{WEBHOOK_PATH}"

@app.route(WEBHOOK_PATH, methods=['POST'])
async def webhook():
    update = types.Update(**request.get_json())
    await dp.feed_update(bot, update)
    return "OK", 200

@app.route("/")
def index():
    return "Bot is running!", 200

async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")

@app.before_first_request
def setup():
    import asyncio
    asyncio.run(on_startup())