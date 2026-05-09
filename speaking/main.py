import asyncio
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

# Flask app для health check
app = Flask(__name__)

@app.route('/')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

async def main():
    # Запускаем Flask в отдельном потоке
    thread = Thread(target=run_flask, daemon=True)
    thread.start()
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())