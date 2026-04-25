import speech_recognition as sr
import tempfile
import os
from pydub import AudioSegment

async def voice_to_text(file_bytes: bytes) -> str:
    """Конвертирует аудио в текст через бесплатный Google Speech Recognition."""
    temp_ogg_path = None
    temp_wav_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp_ogg:
            tmp_ogg.write(file_bytes)
            temp_ogg_path = tmp_ogg.name

        temp_wav_path = tempfile.mktemp(suffix=".wav")
        audio = AudioSegment.from_ogg(temp_ogg_path)
        audio.export(temp_wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav_path) as source:
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(audio_data, language="en-US")

        if temp_ogg_path and os.path.exists(temp_ogg_path):
            os.unlink(temp_ogg_path)
        if temp_wav_path and os.path.exists(temp_wav_path):
            os.unlink(temp_wav_path)

        return text

    except sr.UnknownValueError:
        print("STT ERROR: could not understand")
        return ""
    except Exception as e:
        print(f"STT ERROR: {e}")
        return ""