from elevenlabs import generate, set_api_key, voices
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
import tempfile

set_api_key(ELEVENLABS_API_KEY)

async def text_to_voice(text: str):
    try:
        audio_bytes = generate(
            text=text,
            voice=ELEVENLABS_VOICE_ID,
            model="eleven_monolingual_v1"
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        return tmp_path
    except Exception as e:
        print(f"ElevenLabs TTS error: {e}")
        return None