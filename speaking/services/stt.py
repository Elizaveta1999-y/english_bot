import speech_recognition as sr
import tempfile
import os

async def voice_to_text(file_bytes: bytes) -> str:
    """Конвертирует аудио (ogg, mp3 и др.) в текст через Google Speech Recognition"""
    try:
        # Сохраняем байты во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        # Конвертируем ogg в wav (pydub)
        from pydub import AudioSegment
        wav_path = tmp_path.replace(".ogg", ".wav")
        audio = AudioSegment.from_ogg(tmp_path)
        audio.export(wav_path, format="wav")
        
        # Распознаём
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        
        text = recognizer.recognize_google(audio_data, language="en-US")
        
        # Удаляем временные файлы
        os.unlink(tmp_path)
        os.unlink(wav_path)
        
        return text
    except Exception as e:
        print("STT ERROR:", e)
        return ""