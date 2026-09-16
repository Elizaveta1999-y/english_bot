import os
import json
import base64
import asyncio
import logging
import tempfile
import websockets

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Лимит одновременных генераций на одно WebSocket-соединение
MAX_CONCURRENT_CONTEXTS = 5
_context_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CONTEXTS)

# Дешёвая быстрая модель (в 6 раз дешевле Multilingual v2)
MODEL_ID = "eleven_flash_v2_5"

# Сетевые настройки WebSocket
PING_INTERVAL = 30
PING_TIMEOUT = 30
MAX_RETRIES = 4
RETRY_DELAYS = [2, 4, 8]


async def text_to_voice(text: str, voice_id: str = None):
    """
    Генерирует голос через ElevenLabs WebSocket API (stream-input).
    Модель: Flash v2.5 — дешёвая, быстрая (~75 мс).
    Возвращает путь к mp3-файлу при успехе, None — при сбое.
    """
    if not ELEVENLABS_API_KEY:
        logger.error("ELEVENLABS_API_KEY is not set")
        return None

    if voice_id is None:
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    async with _context_semaphore:
        return await _generate_voice(text, voice_id)


async def _generate_voice(text: str, voice_id: str):
    """Внутренняя функция: открывает WebSocket, отправляет текст, собирает аудио."""

    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
    url += f"?model_id={MODEL_ID}&output_format=mp3_44100_64"

    audio_chunks = []
    context_id = None
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with websockets.connect(
                url,
                additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_TIMEOUT,
            ) as ws:
                # Шаг 1: отправляем начальное сообщение с настройками голоса
                init_message = {
                    "text": " ",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "speed": 0.85,
                    },
                    "generation_config": {
                        "chunk_length_schedule": [120, 160, 250, 290],
                    },
                    "xi_api_key": ELEVENLABS_API_KEY,
                }
                await ws.send(json.dumps(init_message))

                # Шаг 2: отправляем текст
                await ws.send(json.dumps({"text": text}))

                # Шаг 3: сигнал конца текста
                await ws.send(json.dumps({"text": ""}))

                # Шаг 4: читаем ответы
                while True:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    except asyncio.TimeoutError:
                        raise Exception("Таймаут ожидания аудио от ElevenLabs")

                    data = json.loads(message)

                    if data.get("contextId"):
                        context_id = data["contextId"]

                    if data.get("audio"):
                        audio_chunks.append(base64.b64decode(data["audio"]))

                    if data.get("isFinal"):
                        break

                    if data.get("error"):
                        raise Exception(f"ElevenLabs error: {data['error']}")

            if not audio_chunks:
                raise Exception("Пустой аудиоответ от ElevenLabs")

            audio_content = b"".join(audio_chunks)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(audio_content)
                tmp_path = tmp.name

            logger.info(f"TTS (Flash v2.5) generated: {tmp_path} ({len(audio_content)} bytes)")
            return tmp_path

        except websockets.exceptions.ConnectionClosed as e:
            last_error = f"ConnectionClosed: {e}"
            logger.warning(f"TTS WebSocket соединение закрыто (попытка {attempt}/{MAX_RETRIES}): {e}")
        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(f"TTS таймаут (попытка {attempt}/{MAX_RETRIES})")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"TTS WebSocket ошибка (попытка {attempt}/{MAX_RETRIES}): {e}")

            if context_id:
                try:
                    await ws.send(json.dumps({
                        "context_id": context_id,
                        "close_context": True,
                    }))
                except Exception:
                    pass

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            await asyncio.sleep(delay)

    logger.error(f"TTS: все попытки исчерпаны. Последняя ошибка: {last_error}")
    return None