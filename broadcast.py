import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

RECIPIENTS = [
    6115540828,
]

MESSAGE = (
    "Хотим кое-что улучшить в боте — и без тебя не разберёмся.\n\n"
    "Мы молодой проект, поэтому каждый ответ особенно важен.\n\n"
    "Пара коротких вопросов о том, что тебе важно. "
    "А если захочешь поговорить с нами напрямую — нажми «Связаться»."
)

KEYBOARD = {
    "inline_keyboard": [
        [{"text": "📝 Пройти опрос", "callback_data": "start_survey"}],
        [{"text": "💬 Связаться", "callback_data": "start_contact"}],
    ]
}


async def send_to_user(client: httpx.AsyncClient, user_id: int) -> bool:
    try:
        r = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": user_id,
                "text": MESSAGE,
                "reply_markup": KEYBOARD,
                "disable_web_page_preview": True,
            },
        )
        data = r.json()
        if data.get("ok"):
            print(f"✅ {user_id} — отправлено")
            return True
        else:
            print(f"❌ {user_id} — {data.get('description')} (код {data.get('error_code')})")
            return False
    except Exception as e:
        print(f"❌ {user_id} — исключение: {e}")
        return False


async def main():
    print(f"Рассылка на {len(RECIPIENTS)} получателей...")
    ok_count = 0
    fail_count = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for uid in RECIPIENTS:
            if await send_to_user(client, uid):
                ok_count += 1
            else:
                fail_count += 1
            await asyncio.sleep(0.1)
    print(f"\nГотово. Успешно: {ok_count}, не доставлено: {fail_count}")


if __name__ == "__main__":
    asyncio.run(main())