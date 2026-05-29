import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")],
        [InlineKeyboardButton(text="🎭 RolePlay", callback_data="start_roleplay")]
    ])
    await message.answer("Привет! Нажми кнопку.", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking(callback: CallbackQuery):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Кнопка 1"), KeyboardButton(text="Кнопка 2")]],
        resize_keyboard=True
    )
    await callback.message.answer("Голосовой режим. Вот кнопки:", reply_markup=keyboard)
    await callback.answer()

@dp.message(F.text == "Кнопка 1")
async def button1(message: Message):
    await message.answer("Вы нажали Кнопку 1")

@dp.message(F.text == "Кнопка 2")
async def button2(message: Message):
    await message.answer("Вы нажали Кнопку 2")

@dp.message(F.text)
async def echo(message: Message):
    await message.answer(f"Вы написали: {message.text}")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))