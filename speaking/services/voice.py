from aiogram import Router, F
from aiogram.types import Message
import requests
import os

from openai import OpenAI
from speaking.services.ai import process_voice_message

router = Router()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@router.message(F.voice)
async def handle_voice(message: Message):
    try:
        bot = message.bot

        # 1. Получаем файл
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path

        file_url = f"https://api.telegram.org/file/bot{os.getenv('BOT_TOKEN')}/{file_path}"

        # 2. Скачиваем аудио
        response = requests.get(file_url)
        with open("voice.ogg", "wb") as f:
            f.write(response.content)

        print("✅ AUDIO DOWNLOADED")

        # 3. Whisper
        with open("voice.ogg", "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )

        user_text = transcript.text
        print("🧠 USER SAID:", user_text)

        # 4. GPT
        ai_response = await process_voice_message(user_text)
        print("🤖 AI:", ai_response)

        # 5. Отправляем текст сразу (чтобы пользователь не ждал)
        await message.answer(f"🗣 You said: {user_text}\n\n🤖 {ai_response}")

        # 6. Генерация голоса (БЕЗ стриминга)
        speech_file_path = "response.mp3"

        speech = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=ai_response
        )

        with open(speech_file_path, "wb") as f:
            f.write(speech.content)

        print("🔊 VOICE GENERATED")

        # 7. Отправка голосового
        await message.answer_voice(open(speech_file_path, "rb"))

    except Exception as e:
        print("❌ ERROR:", e)
        await message.answer("Something went wrong")