import asyncio
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

# --- 1. НАСТРОЙКА БОТА (ПОЛЛИНГ) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

async def run_bot():
    """Запускает основную логику бота в режиме Long Polling."""
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    print("🚀 Bot started in polling mode")
    await dp.start_polling(bot)

# --- 2. ПРОСТОЙ ВЕБ-СЕРВЕР ДЛЯ HEALTH CHECK (ОТДЕЛЬНЫЙ ПОТОК) ---
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health_check():
    """Этот эндпоинт будет отвечать на проверки Render."""
    return "OK", 200

def run_web_server():
    """Запускает Flask-сервер в отдельном потоке."""
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- 3. ЗАПУСК ВСЕГО СРАЗУ ---
if __name__ == "__main__":
    # Запускаем веб-сервер в фоновом потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    # Запускаем бота в основном потоке asyncio
    asyncio.run(run_bot())