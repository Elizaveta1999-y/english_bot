import requests
import tempfile
import os
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

async def text_to_voice(text: str):
    """Генерирует голос через ElevenLabs API с медленной, естественной речью"""
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.3,          # ниже = более эмоционально, живая речь
                "similarity_boost": 0.8,    # чтобы голос был стабильно узнаваемым
                "speed": 0.85               # медленнее на 15% — против тараторения
            }
        }
        response = requests.post(url, json=data, headers=headers, timeout=15)
        
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name
            return tmp_path
        else:
            print(f"ElevenLabs API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"TTS error: {e}")
        return None