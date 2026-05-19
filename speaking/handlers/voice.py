from aiogram import Router, F
from aiogram.types import Message

router = Router()

@router.message(F.text)
async def echo(message: Message):
    await message.answer(f"Echo: {message.text}")