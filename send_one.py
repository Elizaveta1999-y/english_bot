import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

USER_ID = 6115540828

TEXT = (
    "🎓 <b>У бота появился наставник. Её зовут Айва.</b>\n\n"
    "Она объясняет по-русски — ловит твои ошибки в речи, "
    "объясняет правила, а потом ведёт "
    "мини-уроки для закрепления.\n\n"
    "Не переписка, а настоящее занятие.\n\n"
    "🎁 Дарим тебе 4 голосовых — чтобы попробовать."
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

    try:
        await bot.send_message(USER_ID, TEXT, reply_markup=get_keyboard())
        print(f"✓ Сообщение отправлено {USER_ID}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

    await bot.session.close()


asyncio.run(main())