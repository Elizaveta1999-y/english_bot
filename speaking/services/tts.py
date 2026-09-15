import os
import logging
import asyncio
import tempfile
import aiohttp

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# ---------- НАСТРОЙКИ СЕТИ ----------
REQUEST_TIMEOUT = 90
MAX_RETRIES = 5
RETRY_DELAYS = [2, 4, 8, 16]


async def text_to_voice(text: str, voice_id: str = None):
    """
    Генерирует голос через ElevenLabs API.
    Возвращает путь к mp3-файлу при успехе, None — при сбое.
    """
    if not ELEVENLABS_API_KEY:
        logger.error("ELEVENLABS_API_KEY is not set")
        return None

    if voice_id is None:
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "speed": 0.85
        }
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        text_err = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {text_err[:200]}")
                    audio_content = await resp.read()

            if not audio_content:
                raise Exception("Пустой аудиоответ от ElevenLabs")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(audio_content)
                tmp_path = tmp.name
            logger.info(f"TTS generated: {tmp_path}")
            return tmp_path

        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(f"TTS: таймаут ElevenLabs (попытка {attempt}/{MAX_RETRIES})")
        except aiohttp.ClientError as e:
            last_error = f"client_error: {e}"
            logger.warning(f"TTS: ClientError (попытка {attempt}/{MAX_RETRIES}): {e}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"TTS: ошибка (попытка {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            await asyncio.sleep(delay)

    logger.error(f"TTS: все попытки исчерпаны. Последняя ошибка: {last_error}")
    return None