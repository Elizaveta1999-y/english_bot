from elevenlabs import generate, set_api_key
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
import tempfile
import os

set_api_key(ELEVENLABS_API_KEY)

async def text_to_voice(text: str):
    """Генерирует голос через ElevenLabs и возвращает файл-объект для отправки."""
    try:
        audio_bytes = generate(
            text=text,
            voice=ELEVENLABS_VOICE_ID,
            model="eleven_monolingual_v1"
        )
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        # Возвращаем открытый файл для aiogram
        from aiogram.types import FSInputFile
        return FSInputFile(tmp_path)
    except Exception as e:
        print("TTS ERROR:", e)
        return None