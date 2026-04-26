import tempfile
import os
from faster_whisper import WhisperModel

# Модель будет загружена один раз при первом запросе и сохранится в памяти
model = None

def get_model():
    global model
    if model is None:
        # Используем small модель, так как она оптимальна по скорости и размеру
        # compute_type="int8" позволяет ускорить работу на CPU
        print("Loading Faster-Whisper model (small)...")
        model = WhisperModel("small", device="cpu", compute_type="int8")
        print("Model loaded.")
    return model

async def voice_to_text(file_bytes: bytes) -> str:
    """
    Распознает речь из аудиофайла с помощью faster-whisper.
    """
    temp_path = None
    try:
        # Сохраняем голосовое сообщение во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        # Модель faster-whisper отлично работает с OGG, конвертация не требуется
        asr_model = get_model()
        segments, info = asr_model.transcribe(temp_path, beam_size=5, language="en")

        # Собираем распознанный текст из фрагментов
        transcribed_text = " ".join(segment.text for segment in segments)

        if not transcribed_text:
            print("STT: No text recognized.")
            return ""

        print(f"STT Recognized: {transcribed_text}")
        return transcribed_text

    except Exception as e:
        print(f"STT ERROR: {e}")
        return ""
    finally:
        # Удаляем временный файл в любом случае
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)