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


async def text_to_voice(text: str, voice_id: str = None):
    """
    Генерирует голос через ElevenLabs WebSocket API (stream-input).
    Возвращает путь к mp3-файлу при успехе, None — при сбое.

    WebSocket держит слот только во время активной генерации.
    Пока аудио воспроизводится — слот свободен и может обслуживать других.
    """
    if not ELEVENLABS_API_KEY:
        logger.error("ELEVENLABS_API_KEY is not set")
        return None

    if voice_id is None:
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    # Ограничиваем количество одновременных контекстов
    async with _context_semaphore:
        return await _generate_voice(text, voice_id)


async def _generate_voice(text: str, voice_id: str):
    """Внутренняя функция: открывает WebSocket, отправляет текст, собирает аудио."""

    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
    # Добавляем параметры для стриминга
    url += "?model_id=eleven_multilingual_v2&output_format=mp3_44100_64"

    audio_chunks = []
    context_id = None
    last_error = None

    for attempt in range(1, 4):  # 3 попытки
        try:
            async with websockets.connect(
                url,
                additional_headers={"xi-api-key": ELEVENLABS_API_KEY},
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                # Шаг 1: отправляем начальное сообщение с настройками голоса
                init_message = {
                    "text": " ",  # пробел — обязателен для инициализации
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

                    # Сохраняем context_id для возможного закрытия
                    if data.get("contextId"):
                        context_id = data["contextId"]

                    # Аудио-чанк приходит в base64
                    if data.get("audio"):
                        audio_chunks.append(base64.b64decode(data["audio"]))

                    # Признак конца генерации
                    if data.get("isFinal"):
                        break

                    # Ошибки
                    if data.get("error"):
                        raise Exception(f"ElevenLabs error: {data['error']}")

            # Если дошли сюда — генерация успешна
            if not audio_chunks:
                raise Exception("Пустой аудиоответ от ElevenLabs")

            audio_content = b"".join(audio_chunks)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(audio_content)
                tmp_path = tmp.name

            logger.info(f"TTS (WebSocket) generated: {tmp_path} ({len(audio_content)} bytes)")
            return tmp_path

        except Exception as e:
            last_error = str(e)
            logger.warning(f"TTS WebSocket ошибка (попытка {attempt}/3): {e}")

            # Пытаемся закрыть контекст, если он остался
            if context_id:
                try:
                    await ws.send(json.dumps({
                        "context_id": context_id,
                        "close_context": True,
                    }))
                except Exception:
                    pass

            if attempt < 3:
                await asyncio.sleep(2 ** attempt)  # 2, 4 сек

    logger.error(f"TTS: все попытки исчерпаны. Последняя ошибка: {last_error}")
    return None