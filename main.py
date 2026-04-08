import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN
from speaking.handler import start as speak_start, handle as speak_handle

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [InlineKeyboardButton(text="📝 ОГЭ / ЕГЭ", callback_data="exam")],
        [InlineKeyboardButton(text="🎙 Speaking", callback_data="speak")]
    ])


@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        """Hello! 👋 Я твой персональный учитель английского 🇬🇧

Я помогу тебе в практике языка и разговоре!

👇 Выбери режим:""",
        reply_markup=main_menu()
    )


@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    if call.data == "speak":
        await speak_start(call.message)

    elif call.data == "games":
        await call.message.answer("🎮 Скоро")

    elif call.data == "exam":
        await call.message.answer("📝 Скоро")


@dp.message(F.voice)
async def voice_handler(message: types.Message):
    await speak_handle(message)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())