from aiogram import Router, F
from aiogram.types import Message
import requests
import os

from speaking.services.ai import process_voice_message

router = Router()


@router.message(F.voice)
async def handle_voice(message: Message):
    try:
        print("🔥 VOICE HANDLER TRIGGERED")

        bot = message.bot

        file_id = message.voice.file_id
        print("📁 FILE ID:", file_id)

        file = await bot.get_file(file_id)
        file_path = file.file_path
        print("📁 FILE PATH:", file_path)

        file_url = f"https://api.telegram.org/file/bot{os.getenv('BOT_TOKEN')}/{file_path}"
        print("🌐 FILE URL:", file_url)

        # скачиваем аудио
        response = requests.get(file_url)
        with open("voice.ogg", "wb") as f:
            f.write(response.content)

        print("✅ AUDIO DOWNLOADED")

        # пока без whisper — тестим текстом
        fake_text = "hello"
        print("🧠 FAKE TEXT:", fake_text)

        ai_response = await process_voice_message(fake_text)
        print("🤖 AI RESPONSE:", ai_response)

        await message.answer(ai_response)

    except Exception as e:
        print("❌ ERROR:", e)
        await message.answer("Error happened")