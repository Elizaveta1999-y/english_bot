import os
import tempfile
import logging
import asyncio
import aiohttp
from pydub import AudioSegment

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# ---------- НАСТРОЙКИ СЕТИ ----------
REQUEST_TIMEOUT = 90
MAX_RETRIES = 5
RETRY_DELAYS = [2, 4, 8, 16]


async def voice_to_text(file_bytes: bytes) -> str:
    """
    Распознаёт речь через ElevenLabs Scribe v2 API.
    Возвращает:
      - строку с текстом при успехе (может быть пустой, если речи не было),
      - None при сбое API/сети (чтобы вызывающий код отличил «не распозналось» от «API упал»).
    """
    temp_ogg = None
    temp_wav = None

    try:
        # Сохраняем входящий OGG файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_ogg = f.name

        # Конвертируем в WAV (ElevenLabs Scribe принимает WAV или MP3)
        temp_wav = tempfile.mktemp(suffix=".wav")
        audio = AudioSegment.from_ogg(temp_ogg)
        audio.export(temp_wav, format="wav")

        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": ELEVENLABS_API_KEY}
        data = {
            "model_id": "scribe_v2",
            "language_code": "en",
            "diarize": "false",
            "tag_audio_events": "false"
        }

        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    with open(temp_wav, "rb") as audio_file:
                        form = aiohttp.FormData()
                        form.add_field(
                            "file",
                            audio_file,
                            filename="audio.wav",
                            content_type="audio/wav"
                        )
                        for key, value in data.items():
                            form.add_field(key, value)

                        async with session.post(url, headers=headers, data=form) as resp:
                            if resp.status != 200:
                                text = await resp.text()
                                raise Exception(f"HTTP {resp.status}: {text[:200]}")
                            result = await resp.json()

                text = result.get("text", "")
                return text  # может быть "" если речи нет — это нормально

            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning(f"STT: таймаут ElevenLabs (попытка {attempt}/{MAX_RETRIES})")
            except aiohttp.ClientError as e:
                last_error = f"client_error: {e}"
                logger.warning(f"STT: ClientError (попытка {attempt}/{MAX_RETRIES}): {e}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"STT: ошибка (попытка {attempt}/{MAX_RETRIES}): {e}")

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
                await asyncio.sleep(delay)

        logger.error(f"STT: все попытки исчерпаны. Последняя ошибка: {last_error}")
        return None

    except Exception as e:
        logger.error(f"STT: критическая ошибка: {e}", exc_info=True)
        return None

    finally:
        if temp_ogg and os.path.exists(temp_ogg):
            try:
                os.unlink(temp_ogg)
            except Exception:
                pass
        if temp_wav and os.path.exists(temp_wav):
            try:
                os.unlink(temp_wav)
            except Exception:
                pass