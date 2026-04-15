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

        # 3. Whisper (распознавание речи)
        with open("voice.ogg", "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )

        user_text = transcript.text
        print("🧠 USER SAID:", user_text)

        # 4. GPT ответ
        ai_response = await process_voice_message(user_text)
        print("🤖 AI:", ai_response)

        # 5. Генерация голосового ответа
        speech_file_path = "response.mp3"

        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=ai_response,
        ) as response:
            response.stream_to_file(speech_file_path)

        # 6. Отправляем и текст, и голос
        await message.answer(f"🗣 You said: {user_text}\n\n🤖 {ai_response}")
        await message.answer_voice(open(speech_file_path, "rb"))

    except Exception as e:
        print("❌ ERROR:", e)
        await message.answer("Something went wrong")