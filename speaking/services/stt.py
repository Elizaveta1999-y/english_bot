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

SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 250
CHUNK_SEND_INTERVAL = 0.20

PING_INTERVAL = 30
PING_TIMEOUT = 30
MAX_RETRIES = 4
RETRY_DELAYS = [2, 4, 8]


async def voice_to_text(file_bytes: bytes) -> str:
    if not ELEVENLABS_API_KEY:
        logger.error("STT: ELEVENLABS_API_KEY не задан")
        return None

    temp_ogg = None
    temp_pcm = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_ogg = f.name

        temp_pcm = tempfile.mktemp(suffix=".pcm")
        audio = AudioSegment.from_ogg(temp_ogg)
        audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
        audio.export(temp_pcm, format="raw")

        with open(temp_pcm, "rb") as f:
            pcm_data = f.read()

        logger.info(f"STT: PCM {len(pcm_data)} байт (~{len(pcm_data) / (SAMPLE_RATE * 2):.1f} сек)")

        url = (
            "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
            f"?model_id=scribe_v2_realtime"
            f"&audio_format=pcm_{SAMPLE_RATE}"
            f"&language_code=en"
            f"&commit_strategy=manual"
            f"&include_timestamps=false"
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
                    max_size=None,
                    max_queue=256,
                ) as ws:
                    chunk_size = int(SAMPLE_RATE * 2 * (CHUNK_DURATION_MS / 1000))
                    total_chunks = (len(pcm_data) + chunk_size - 1) // chunk_size

                    for idx, i in enumerate(range(0, len(pcm_data), chunk_size)):
                        chunk = pcm_data[i:i + chunk_size]
                        is_last = (idx == total_chunks - 1)
                        msg = {
                            "message_type": "input_audio_chunk",
                            "audio_base_64": base64.b64encode(chunk).decode(),
                            "sample_rate": SAMPLE_RATE,
                            "commit": is_last,   # commit только на последнем чанке
                        }
                        await ws.send(json.dumps(msg))
                        await asyncio.sleep(CHUNK_SEND_INTERVAL)

                    # Читаем ответы
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

                        elif msg_type in ("error", "auth_error", "quota_exceeded",
                                          "input_error", "transcriber_error"):
                            raise Exception(f"STT error: {data.get('error', msg_type)}")

                if collected_texts:
                    return " ".join(collected_texts).strip()

            except websockets.exceptions.ConnectionClosedOK:
                if collected_texts:
                    full_text = " ".join(collected_texts).strip()
                    if full_text:
                        return full_text
                last_error = "ConnectionClosedOK (no text)"
            except websockets.exceptions.ConnectionClosed as e:
                last_error = f"ConnectionClosed: {e}"
                if collected_texts:
                    full_text = " ".join(collected_texts).strip()
                    if full_text:
                        return full_text
            except asyncio.TimeoutError:
                last_error = "timeout"
                if collected_texts:
                    full_text = " ".join(collected_texts).strip()
                    if full_text:
                        return full_text
            except Exception as e:
                last_error = str(e)
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