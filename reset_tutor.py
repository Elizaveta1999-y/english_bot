import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

USER_ID = 6115540828  # твой Telegram ID

async def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL не найден в .env")
        return
    conn = await asyncpg.connect(url)
    await conn.execute("DELETE FROM tutor_memory WHERE user_id = $1", USER_ID)
    await conn.execute("UPDATE users SET state = '{}'::jsonb WHERE user_id = $1", USER_ID)
    await conn.close()
    print(f"Память Наставника и state для {USER_ID} сброшены.")

asyncio.run(main())