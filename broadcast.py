import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

# ================= СПИСОК ПОЛУЧАТЕЛЕЙ =================
RECIPIENTS = [
    6115540828,   # ты
    8989851203,
    8935751913,
    8805178403,
    8783263150,
    8635614210,
    8587249438,
    8455147637,
    8377498968,
    8358579113,
    8277695572,
    8128342132,
    7994596651,
    7948348493,
    7932877841,
    7920589849,
    7854123041,
    7485692671,
    7297448159,
    7242935930,
    7231231109,
]

# ================= ТЕКСТ СООБЩЕНИЯ =================
MESSAGE = (
    "Приятное обновление 🤍\n\n"
    "Раньше был один тариф, теперь два — на спокойный темп и на интенсивный. "
    "Чтобы каждый нашёл своё.\n\n"
    "Загляни, если хочется посмотреть."
)

KEYBOARD = {
    "inline_keyboard": [
        [{"text": "💎 Посмотреть тарифы", "callback_data": "show_tariffs"}],
    ]
}
# ===================================================


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