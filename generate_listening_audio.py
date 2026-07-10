import os
import json
import asyncio
from dotenv import load_dotenv
from speaking.services.tts import text_to_voice

load_dotenv()
os.environ["ELEVENLABS_API_KEY"] = os.getenv("ELEVENLABS_API_KEY", "")

TASKS_FILE = "data/listening_tasks.json"
OUTPUT_DIR = "audio_temp"

# Голоса
VOICE_MALE = "PUnlEy1oTSskvd4umq6Q"   # замените на свой
VOICE_FEMALE = "acCWxmzPBgXdHwA63uzP"   # замените на свой

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(TASKS_FILE, "r", encoding="utf-8") as f:
    tasks = json.load(f)

def choose_voice(text: str, task_id: int) -> str:
    female_markers = ["anna", "sister", "she", "her", "ms.", "mrs.", "woman", "girl", "lily", "mary", "jane", "emma"]
    male_markers = ["tom", "jerry", "he", "him", "mr.", "man", "boy", "john", "peter", "michael"]
    text_lower = text.lower()
    for marker in female_markers:
        if marker in text_lower:
            return VOICE_FEMALE
    for marker in male_markers:
        if marker in text_lower:
            return VOICE_MALE
    # Если не определилось — чередуем по id
    return VOICE_FEMALE if task_id % 2 == 0 else VOICE_MALE

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
        voice = choose_voice(audio_text, task_id)
        print(f"🎤 Выбран голос: {'женский' if voice == VOICE_FEMALE else 'мужской'}")

        mp3_path = await text_to_voice(audio_text, voice_id=voice)
        if mp3_path and os.path.exists(mp3_path):
            os.rename(mp3_path, file_path)
            print(f"✅ Сохранено: {file_path}")
        else:
            print(f"❌ Ошибка генерации для {task_id}")

    print("🎉 Готово!")

if __name__ == "__main__":
    asyncio.run(main())