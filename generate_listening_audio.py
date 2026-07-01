import os
from dotenv import load_dotenv
load_dotenv()

# === ЯВНО ПЕРЕДАЁМ КЛЮЧ В ОКРУЖЕНИЕ ===
os.environ["ELEVENLABS_API_KEY"] = os.getenv("ELEVENLABS_API_KEY", "")

import json
import asyncio
from speaking.services.tts import text_to_voice

TASKS_FILE = "data/listening_tasks.json"
OUTPUT_DIR = "audio_temp"

# Голоса (ваши ID)
VOICE_MALE = "uYXf8XasLslADfZ2MB4u"
VOICE_FEMALE = "nucVFUFVgPmKHjgXNbJ7"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(TASKS_FILE, "r", encoding="utf-8") as f:
    tasks = json.load(f)

async def main():
    for task in tasks:
        task_id = task["id"]
        level = task["level"]
        task_type = task["type"]
        audio_text = task["audio_text"]

        file_path = os.path.join(OUTPUT_DIR, f"{level}_{task_type}_{task_id}.mp3")
        if os.path.exists(file_path):
            print(f"⏩ Уже есть: {file_path}")
            continue

        print(f"🔊 Генерирую: {level}/{task_type}/{task_id}")
        voice = VOICE_MALE if task_id % 2 == 0 else VOICE_FEMALE
        mp3_path = await text_to_voice(audio_text, voice_id=voice)
        if mp3_path and os.path.exists(mp3_path):
            os.rename(mp3_path, file_path)
            print(f"✅ Сохранено: {file_path}")
        else:
            print(f"❌ Ошибка генерации для {task_id}")

    print("🎉 Готово! Все файлы сохранены в папку audio_temp")

if __name__ == "__main__":
    asyncio.run(main())