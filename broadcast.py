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
    6115540828,
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
        # Печатаем полный ответ Telegram — для отладки
        print(f"→ Ответ Telegram для {user_id}: {data}")
        if data.get("ok"):
            print(f"✅ {user_id} — отправлено")
            return True
        else:
            print(f"❌ {user_id} — ошибка: {data.get('description')} (код {data.get('error_code')})")
            return False
    except Exception as e:
        print(f"❌ {user_id} — исключение: {e}")
        return False


async def main():
    print(f"Рассылка на {len(RECIPIENTS)} получателей...")
    async with httpx.AsyncClient(timeout=15) as client:
        for uid in RECIPIENTS:
            await send_to_user(client, uid)
            await asyncio.sleep(0.1)
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())