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
    5004569046,
    1949534208,
    1930910667,
    1882660819,
    1714835720,
    1557630977,
    1361031819,
    1335656337,
    1257408427,
    1113092602,
    1067666122,
    1059468458,
    1058488664,
    1058327288,
    969167136,
    762142261,
    757262605,
    754685539,
    688596957,
    652838482,
    412043474,
    373777014,
    109978207,
    109090438,
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