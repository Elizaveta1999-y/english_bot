import os
import aiohttp
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def download_file(url: str, path: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()
            with open(path, "wb") as f:
                f.write(data)


async def transcribe_audio(file_url: str) -> str:
    try:
        file_path = "voice.ogg"

        # скачиваем файл
        await download_file(file_url, file_path)

        # отправляем в openai
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )

        return transcript.text

    except Exception as e:
        print("WHISPER ERROR:", e)
        return None


async def ask_ai(text: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a friendly English teacher.
Correct mistakes, explain briefly, and keep conversation going."""
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        )

        return response.choices[0].message.content

    except Exception as e:
        print("GPT ERROR:", e)
        return "Something went wrong"