import requests
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

async def text_to_voice(text: str, voice_id: str = None):
    """Генерирует голос через ElevenLabs API."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        logger.error("ELEVENLABS_API_KEY is not set")
        return None
    
    if voice_id is None:
        # Можно задать голос по умолчанию или взять из окружения
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
"voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "speed": 0.70   # основное — снижаем скорость
}
        }
        response = requests.post(url, json=data, headers=headers, timeout=45)
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