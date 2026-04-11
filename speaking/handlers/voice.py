import requests
from aiogram.types import Message, FSInputFile

from .start import speaking_users
from services.ai import ask_ai
from services.tts import text_to_speech


async def handle_voice(message: Message):
    user_id = message.from_user.id

    if user_id not in speaking_users:
        return

    await message.answer("🎧 Слушаю...")

    file = await message.bot.get_file(message.voice.file_id)
    file_path = file.file_path

    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file_path}"
    audio = requests.get(file_url)

    with open("voice.ogg", "wb") as f:
        f.write(audio.content)

    await message.answer("🧠 Думаю...")

    # пока тестовый текст
    user_text = "Hello"

    ai_answer = await ask_ai(user_text)

    audio_file = text_to_speech(ai_answer)

    voice = FSInputFile(audio_file)

    await message.answer_voice(voice)