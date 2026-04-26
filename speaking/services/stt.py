import speech_recognition as sr
import tempfile
import os
from pydub import AudioSegment

async def voice_to_text(file_bytes: bytes) -> str:
    """Распознаёт речь через Google Speech Recognition (бесплатно)"""
    temp_ogg = None
    temp_wav = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_ogg = f.name

        temp_wav = tempfile.mktemp(suffix=".wav")
        audio = AudioSegment.from_ogg(temp_ogg)
        audio.export(temp_wav, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(audio_data, language="en-US")
        
        # Очистка от возможного мусора
        import re
        text = re.sub(r'\b(download free|the internet|stuff|really weird|free the book)\b', '', text, flags=re.IGNORECASE)
        text = ' '.join(text.split())
        
        os.unlink(temp_ogg)
        os.unlink(temp_wav)
        return text.strip()
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"STT ERROR: {e}")
        return ""