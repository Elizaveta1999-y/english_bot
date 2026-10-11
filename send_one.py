import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

USER_IDS = [
    7297448159,
    109090438,
    412043474,
]

TEXT = (
    "Спасибо, что приняла участие в опросе 🤍\n\n"
    "🎓 <b>У бота появился наставник. Её зовут Айва.</b>\n\n"
    "Она объясняет по-русски — ловит твои ошибки в речи, "
    "разбирает правило, а потом ведёт мини-урок для закрепления.\n\n"
    "Не переписка, а настоящее занятие.\n\n"
    "🎁 Дарим тебе 10 голосовых — чтобы ты оценила"
)


def get_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Открыть Айву", callback_data="start_tutor")],
    ])


async def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не найден в .env")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

    sent = 0
    failed = 0

    for uid in USER_IDS:
        try:
            await bot.send_message(uid, TEXT, reply_markup=get_keyboard())
            print(f"✓ {uid}")
            sent += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"✗ {uid}: {e}")
            failed += 1

    print(f"\nИтого: отправлено {sent}, ошибок {failed}")
    await bot.session.close()


asyncio.run(main())