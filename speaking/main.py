import asyncio
import threading
import http.server
import socketserver
import sys
import os

# 🔥 фикс путей (ЭТО КЛЮЧЕВОЕ)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher

from handlers.start import router as start_router
from handlers.voice import router as voice_router

BOT_TOKEN = "YOUR_BOT_TOKEN"


def start_dummy_server():
    PORT = 10000
    Handler = http.server.SimpleHTTPRequestHandler

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(voice_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    threading.Thread(target=start_dummy_server).start()
    asyncio.run(main())