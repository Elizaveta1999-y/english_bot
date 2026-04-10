from aiogram.types import Message
from .start import speaking_users

async def handle_voice(message: Message):
    user_id = message.from_user.id

    if user_id not in speaking_users:
        return

    await message.answer("🎧 Голос получил, думаю...")

    # ПОКА ПРОСТО ОТВЕТ
    await message.answer("Hello! I heard you 😄")