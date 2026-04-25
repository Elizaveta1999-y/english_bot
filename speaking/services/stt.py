import speech_recognition as sr
import tempfile
import os
from pydub import AudioSegment

async def voice_to_text(file_bytes: bytes) -> str:
    """Конвертирует аудио в текст, используя бесплатный Google Speech Recognition."""
    temp_ogg_path = None
    temp_wav_path = None
    try:
        # Сохраняем во временный OGG файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp_ogg:
            tmp_ogg.write(file_bytes)
            temp_ogg_path = tmp_ogg.name

        # Конвертируем OGG в WAV
        temp_wav_path = tempfile.mktemp(suffix=".wav")
        audio = AudioSegment.from_ogg(temp_ogg_path)
        audio.export(temp_wav_path, format="wav")

        # Распознаем речь
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav_path) as source:
            audio_data = recognizer.record(source)

        # Используем Google Speech Recognition (бесплатно, без ключа)
        text = recognizer.recognize_google(audio_data, language="en-US")

        # Очищаем временные файлы
        if temp_ogg_path and os.path.exists(temp_ogg_path):
            os.unlink(temp_ogg_path)
        if temp_wav_path and os.path.exists(temp_wav_path):
            os.unlink(temp_wav_path)

        return text

    except sr.UnknownValueError:
        print("STT ERROR: Google Speech Recognition could not understand audio")
        return ""
    except sr.RequestError as e:
        print(f"STT ERROR: Could not request results from Google Speech Recognition service; {e}")
        return ""
    except Exception as e:
        print(f"STT ERROR: {e}")
        return ""