import asyncio
from monetization.sub import users

async def reminder(bot):
    while True:
        for uid, u in users.items():
            await bot.send_message(uid, "Вернись в бот ❤️")
        await asyncio.sleep(86400)