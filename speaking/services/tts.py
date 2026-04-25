from elevenlabs import generate, set_api_key
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
import tempfile

set_api_key(ELEVENLABS_API_KEY)

async def text_to_voice(text: str) -> bytes:
    """Генерирует голос через ElevenLabs и возвращает MP3 в виде байтов"""
    try:
        audio_bytes = generate(
            text=text,
            voice=ELEVENLABS_VOICE_ID,
            model="eleven_monolingual_v1"
        )
        return audio_bytes
    except Exception as e:
        print("TTS ERROR:", e)
        return None