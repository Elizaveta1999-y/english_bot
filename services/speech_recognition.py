import os
import aiohttp
import aiofiles

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

async def speech_to_text(file_path: str, model_id: str = "scribe_v1") -> str:
    """
    Отправляет аудиофайл в ElevenLabs для распознавания.
    Возвращает распознанный текст.
    """
    if not ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY не задан в переменных окружения")

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY
    }

    async with aiofiles.open(file_path, "rb") as f:
        audio_data = await f.read()

    data = aiohttp.FormData()
    data.add_field("file", audio_data, filename=file_path, content_type="audio/ogg")
    data.add_field("model_id", model_id)  # Используем scribe_v1 (или scribe_v2)

    async with aiohttp.ClientSession() as session:
        async with session.post(ELEVENLABS_STT_URL, headers=headers, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"ElevenLabs STT error: {resp.status} - {error_text}")
            result = await resp.json()
            return result.get("text", "")