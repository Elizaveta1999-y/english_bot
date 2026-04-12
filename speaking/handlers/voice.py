from aiogram import Router, F
from aiogram.types import Message

from handlers.start import speaking_users
from services.ai import ask_ai
from services.tts import text_to_speech

router = Router()


@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id

    if user_id not in speaking_users:
        return

    user_text = "Hello, I want to practice English"

    ai_response = await ask_ai(user_text)

    audio_file = await text_to_speech(ai_response)

    await message.answer_voice(audio_file)