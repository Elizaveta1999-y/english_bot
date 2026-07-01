import os
import json
import random
import asyncio
import boto3
from botocore.client import Config
from speaking.services.tts import text_to_voice  # ваша асинхронная функция
from dotenv import load_dotenv
load_dotenv()

# ===== НАСТРОЙКИ =====
TASKS_FILE = "data/listening_tasks.json"
OUTPUT_DIR = "audio_temp"

# ElevenLabs голоса
VOICE_MALE = "uYXf8XasLslADfZ2MB4u"
VOICE_FEMALE = "nucVFUFVgPmKHjgXNbJ7"

# Cloudflare R2
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_ENDPOINT = "https://688baf9f3b63b6f8fe6e2e9d627633c9.r2.cloudflarestorage.com"
R2_BUCKET = "listening-audio"

# Инициализация R2 клиента (синхронный, но используем в асинхронной функции)
s3 = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=Config(signature_version='s3v4')
)

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    for task in tasks:
        task_id = task["id"]
        level = task["level"]
        task_type = task["type"]
        audio_text = task["audio_text"]

        audio_key = f"{level}/{task_type}/{task_id}.mp3"

        # Проверяем наличие в R2
        try:
            s3.head_object(Bucket=R2_BUCKET, Key=audio_key)
            print(f"✅ Уже есть: {audio_key}")
            continue
        except:
            print(f"🔊 Генерирую: {audio_key}")

        # Выбор голоса (можно усложнить, анализируя текст)
        voice = random.choice([VOICE_MALE, VOICE_FEMALE])

        # Генерируем аудио (асинхронно)
        mp3_path = await text_to_voice(audio_text, voice_id=voice)
        if not mp3_path or not os.path.exists(mp3_path):
            print(f"❌ Ошибка генерации для {task_id}")
            continue

        # Загружаем в R2
        try:
            with open(mp3_path, "rb") as f:
                s3.put_object(
                    Bucket=R2_BUCKET,
                    Key=audio_key,
                    Body=f,
                    ContentType="audio/mpeg"
                )
            print(f"✅ Загружено: {audio_key}")
            os.unlink(mp3_path)  # удаляем временный файл
        except Exception as e:
            print(f"❌ Ошибка загрузки: {e}")

    print("🎉 Готово!")

if __name__ == "__main__":
    asyncio.run(main())