import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args):
        pass  # suppress logs

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

async def main():
    # Запускаем HTTP-сервер для health check в отдельном потоке
    thread = Thread(target=run_web_server, daemon=True)
    thread.start()
    # Даём серверу время запуститься
    await asyncio.sleep(0.5)
    # Устанавливаем команды бота
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    # Запускаем polling (основной процесс)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())