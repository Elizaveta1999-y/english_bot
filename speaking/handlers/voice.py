from aiogram import Router, F
from aiogram.types import Message

router = Router()

@router.message()
async def catch_all(message: Message):
    await message.answer(f"Получено: {message.text if message.text else 'голосовое сообщение'}")