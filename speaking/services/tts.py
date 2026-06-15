import requests
import tempfile
import os
import logging
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

logger = logging.getLogger(__name__)

async def text_to_voice(text: str, voice_id: str = None):
    """Генерирует голос через ElevenLabs API. Если voice_id не указан, использует из config."""
    if not ELEVENLABS_API_KEY:
        logger.error("ELEVENLABS_API_KEY is not set")
        return None
    if voice_id is None:
        from config import ELEVENLABS_VOICE_ID
        voice_id = ELEVENLABS_VOICE_ID
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.3,
                "similarity_boost": 0.8,
                "speed": 0.85
            }
        }
        response = requests.post(url, json=data, headers=headers, timeout=15)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name
            logger.info(f"TTS generated: {tmp_path}")
            return tmp_path
        else:
            logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None