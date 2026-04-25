import tempfile
import os
from faster_whisper import WhisperModel

# Модель загружается один раз при первом вызове (кэшируется)
_model = None

def get_model():
    global _model
    if _model is None:
        # Используем small модель (хороший баланс скорость/качество)
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model

async def voice_to_text(file_bytes: bytes) -> str:
    """Распознаёт речь через faster-whisper (локально, бесплатно, высокое качество)"""
    temp_audio = None
    try:
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(file_bytes)
            temp_audio = tmp.name

        # Конвертируем ogg в wav (Whisper лучше работает с wav)
        from pydub import AudioSegment
        temp_wav = tempfile.mktemp(suffix=".wav")
        audio = AudioSegment.from_ogg(temp_audio)
        audio.export(temp_wav, format="wav")

        # Распознаём
        model = get_model()
        segments, _ = model.transcribe(temp_wav, language="en", beam_size=5)
        text = " ".join(segment.text for segment in segments)

        # Очистка
        os.unlink(temp_audio)
        os.unlink(temp_wav)

        return text.strip()

    except Exception as e:
        print(f"STT ERROR: {e}")
        return ""