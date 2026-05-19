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
        print("✅ Lock acquired, starting bot...")
        return lock_fd
    except (IOError, OSError):
        print("❌ Another instance is already running. Exiting.")
        sys.exit(0)

lock_fd = acquire_lock()

# === НАСТРОЙКА БОТА (POLLING) ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

async def run_bot():
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    print("🚀 Bot started in polling mode")
    await dp.start_polling(bot)

# === ВЕБ-СЕРВЕР ДЛЯ HEALTH CHECK (ОТДЕЛЬНЫЙ ПОТОК) ===
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health_check():
    return "OK", 200

def run_web_server():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# === ЗАПУСК ===
if __name__ == "__main__":
    # Запускаем веб-сервер в фоновом потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    # Запускаем бота в основном потоке
    asyncio.run(run_bot())