import os
import asyncio
import threading
import fcntl
import sys
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

# === БЛОКИРОВКА – только один экземпляр ===
LOCK_FILE = "/tmp/bot.lock"

def acquire_lock():
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (IOError, OSError):
        print("Another instance is already running. Exiting.")
        sys.exit(0)

lock_fd = acquire_lock()

# === БОТ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

async def run_bot():
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    await dp.start_polling(bot)

# === HEALTH CHECK (Flask) ===
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(run_bot())