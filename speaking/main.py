import asyncio
import os
import fcntl
import sys
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from speaking.handlers.start import router as start_router
from speaking.handlers.voice import router as voice_router

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(voice_router)

LOCK_FILE = "/tmp/bot.pid"

def acquire_lock():
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        print(f"Lock acquired, PID: {os.getpid()}")
        return lock_fd
    except (IOError, OSError):
        print("Another instance is running. Exiting.")
        sys.exit(0)

async def main():
    lock_fd = acquire_lock()
    await bot.set_my_commands([
        BotCommand(command="start", description="Start bot"),
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())