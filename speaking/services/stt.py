import os
import json
import base64
import asyncio
import logging
import tempfile
import websockets
from pydub import AudioSegment

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Формат аудио для реалтайм-распознавания
SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 100  # отправляем чанки по 100 мс

# Сетевые настройки WebSocket
PING_INTERVAL = 30
PING_TIMEOUT = 30
MAX_RETRIES = 4
RETRY_DELAYS = [2, 4, 8]


async def voice_to_text(file_bytes: bytes) -> str:
    """
    Распознаёт речь через ElevenLabs Scribe v2 Realtime (WebSocket).
    Возвращает:
      - строку с текстом при успехе (может быть пустой, если речи не было),
      - None при сбое API/сети.
    """
    if not ELEVENLABS_API_KEY:
        logger.error("STT: ELEVENLABS_API_KEY не задан")
        return None

    temp_ogg = None
    temp_pcm = None

    try:
        # Сохраняем OGG
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_ogg = f.name

        # Конвертируем в PCM 16kHz mono (формат для реалтайма)
        temp_pcm = tempfile.mktemp(suffix=".pcm")
        audio = AudioSegment.from_ogg(temp_ogg)
        audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
        audio.export(temp_pcm, format="raw")

        # Читаем PCM целиком
        with open(temp_pcm, "rb") as f:
            pcm_data = f.read()

        logger.warning(f"STT: размер PCM {len(pcm_data)} байт (~{len(pcm_data) / (SAMPLE_RATE * 2):.1f} сек)")

        # URL с параметрами
        url = (
            "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
            f"?model_id=scribe_v2_realtime"
            f"&audio_format=pcm_{SAMPLE_RATE}"
            f"&language_code=en"
            f"&commit_strategy=vad"
            f"&vad_silence_threshold_secs=1.0"
            f"&include_timestamps=false"
            f"&inactivity_timeout=300"
        )

        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            collected_texts = []
            try:
                async with websockets.connect(
                    url,
                    additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
                    ping_interval=PING_INTERVAL,
                    ping_timeout=PING_TIMEOUT,
                    max_size=None,  # снимаем лимит 1 МБ — иначе длинное аудио рвёт соединение
                ) as ws:
                    # Отправляем аудио чанками
                    chunk_size = int(SAMPLE_RATE * 2 * (CHUNK_DURATION_MS / 1000))
                    total_chunks = (len(pcm_data) + chunk_size - 1) // chunk_size
                    logger.warning(f"STT: отправка {total_chunks} чанков (попытка {attempt}/{MAX_RETRIES})")

                    for i in range(0, len(pcm_data), chunk_size):
                        chunk = pcm_data[i:i + chunk_size]
                        msg = {
                            "message_type": "input_audio_chunk",
                            "audio_base_64": base64.b64encode(chunk).decode(),
                            "sample_rate": SAMPLE_RATE,
                        }
                        await ws.send(json.dumps(msg))

                    # Сигнал конца потока
                    await ws.send(json.dumps({
                        "message_type": "input_audio_chunk",
                        "audio_base_64": "",
                        "commit": True,
                    }))

                    # Читаем ответы, пока не упрёмся в таймаут
                    while True:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                        except asyncio.TimeoutError:
                            break

                        data = json.loads(message)
                        msg_type = data.get("message_type")

                        if msg_type == "partial_transcript":
                            pass

                        elif msg_type == "committed_transcript":
                            text = data.get("text", "")
                            if text:
                                collected_texts.append(text)
                                logger.warning(f"STT: committed фрагмент ({len(text)} симв.)")

                        elif msg_type in ("error", "auth_error", "quota_exceeded"):
                            raise Exception(f"STT error: {data.get('error', msg_type)}")

                if collected_texts:
                    full_text = " ".join(collected_texts).strip()
                    logger.warning(f"STT: успешно распознано {len(full_text)} символов за {attempt} попыток")
                    return full_text

            except websockets.exceptions.ConnectionClosed as e:
                last_error = f"ConnectionClosed: {e}"
                logger.warning(f"STT WebSocket соединение закрыто (попытка {attempt}/{MAX_RETRIES}): {e}")
                if collected_texts:
                    full_text = " ".join(collected_texts).strip()
                    if full_text:
                        logger.warning(f"STT: соединение закрылось, но собрано {len(full_text)} символов")
                        return full_text
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning(f"STT таймаут (попытка {attempt}/{MAX_RETRIES})")
                if collected_texts:
                    full_text = " ".join(collected_texts).strip()
                    if full_text:
                        return full_text
            except Exception as e:
                last_error = str(e)
                logger.warning(f"STT WebSocket ошибка (попытка {attempt}/{MAX_RETRIES}): {e}")
                if collected_texts:
                    full_text = " ".join(collected_texts).strip()
                    if full_text:
                        return full_text

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
                await asyncio.sleep(delay)

        logger.error(f"STT: все попытки исчерпаны. Последняя ошибка: {last_error}")
        return None

    except Exception as e:
        logger.error(f"STT: критическая ошибка: {e}", exc_info=True)
        return None

    finally:
        for path in (temp_ogg, temp_pcm):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass