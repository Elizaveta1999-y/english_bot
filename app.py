import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from speaking.handlers.start import router as start_router

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)

# Прямой обработчик всех сообщений (включая текст и callback_query)
@dp.message()
async def catch_all_messages(message: types.Message):
    await message.answer(f"🔥 Прямой обработчик: {message.text}")

WEBHOOK_PATH = "/webhook"

async def handle_webhook(request):
    try:
        data = await request.json()
        logging.info(f"Webhook received data: {data}")
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(text="OK", status=200)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return web.Response(text="Error", status=500)

async def health(request):
    return web.Response(text="Bot is running", status=200)

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)
app.router.add_get("/", health)

async def on_startup(app):
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to {webhook_url}")

app.on_startup.append(on_startup)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    web.run_app(app, host='0.0.0.0', port=port)