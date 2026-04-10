import os
from aiogram.types import Message
from .start import speaking_users
from services.ai import ask_gpt

async def handle_voice(message: Message):
    user_id = message.from_user.id

    if user_id not in speaking_users:
        return

    await message.answer("🎧 Слушаю...")

    # скачиваем файл
    file = await message.bot.get_file(message.voice.file_id)
    file_path = file.file_path

    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file_path}"

    import requests
    audio = requests.get(file_url)

    with open("voice.ogg", "wb") as f:
        f.write(audio.content)

    await message.answer("🧠 Думаю...")

    # 👉 пока заглушка вместо распознавания
    text = "Hello"  # ПОКА ТЕСТ

    ai_answer = await ask_gpt(text)

    await message.answer(f"🤖 {ai_answer}")