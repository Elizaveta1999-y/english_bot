from aiogram import types

async def start(message: types.Message):
    await message.answer("Привет!")