import asyncio
import aiohttp

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------- МЕНЮ ----------
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [InlineKeyboardButton(text="📝 ОГЭ / ЕГЭ", callback_data="exam")],
        [InlineKeyboardButton(text="🎙 Speaking", callback_data="speak")]
    ])


# ---------- СТАРТ ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        """Hello! 👋 Я твой персональный учитель английского 🇬🇧

Я помогу тебе:
— прокачать разговорный английский
— подготовиться к экзаменам
— играть и учить слова

👇 Выбери режим:""",
        reply_markup=main_menu()
    )


# ---------- КНОПКИ ----------
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):

    if call.data == "speak":
        await call.message.answer("🎙 Режим speaking включен. Отправь голос")

    elif call.data == "games":
        await call.message.answer("🎮 Игры скоро тут")

    elif call.data == "exam":
        await call.message.answer("📝 Экзамен скоро тут")


# ---------- ГОЛОС ----------
@dp.message(F.voice)
async def handle_voice(message: types.Message):
    await message.answer("Голос получил 👍")


# ---------- ТЕКСТ (ТЕСТ) ----------
@dp.message()
async def test(message: types.Message):
    await message.answer("Я вижу сообщение")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())