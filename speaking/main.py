import asyncio
import os
import socket
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

async def fake_health_check():
    """Запускает простой TCP-сервер, который ничего не делает, но держит порт открытым."""
    port = int(os.environ.get("PORT", 10000))
    loop = asyncio.get_event_loop()
    server = await loop.create_server(lambda: HealthCheckHandler(), host='0.0.0.0', port=port)
    print(f"Fake health check server listening on port {port}")
    await server.serve_forever()

class HealthCheckHandler(asyncio.Protocol):
    def connection_made(self, transport):
        transport.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        transport.close()

async def main():
    # Запускаем фальшивый health check в фоне
    asyncio.create_task(fake_health_check())
    # Даём время на запуск
    await asyncio.sleep(1)
    # Устанавливаем команды бота
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    # Запускаем polling – единственный вызов getUpdates
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())