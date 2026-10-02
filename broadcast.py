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
    6115540828,   # ты (для контроля)
    7200609134,
    6858571446,
    6627798840,
    6534110789,
    6327199663,
    6311511471,
    6176885277,
    6135159046,
    6056031530,
    5559321856,
    5547341077,
    5515611002,
    5473600795,
    5441688075,
    5293299355,
    5207491023,
    5172674286,
    5124281949,
    5114223254,
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