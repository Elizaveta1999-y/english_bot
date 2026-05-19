from aiogram import Router, types

router = Router()

@router.message()
async def catch_all(message: types.Message):
    await message.answer(f"Catch all: {message.text}")