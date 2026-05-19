from aiogram import Router, types

router = Router()

@router.message()
async def debug_handler(message: types.Message):
    await message.answer(f"DEBUG: получено сообщение: {message.text}")