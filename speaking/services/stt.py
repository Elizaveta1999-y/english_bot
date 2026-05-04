import os
import tempfile
import requests
from pydub import AudioSegment

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

async def voice_to_text(file_bytes: bytes) -> str:
    """
    Распознаёт речь через ElevenLabs Scribe v2 API
    Документация: https://elevenlabs.io/docs/api-reference/scribe
    """
    temp_ogg = None
    temp_wav = None
    
    try:
        # Сохраняем входящий OGG файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_ogg = f.name
        
        # Конвертируем в WAV (ElevenLabs Scribe принимает WAV или MP3)
        temp_wav = tempfile.mktemp(suffix=".wav")
        audio = AudioSegment.from_ogg(temp_ogg)
        audio.export(temp_wav, format="wav")
        
        # Отправляем запрос к ElevenLabs Scribe API
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        
        with open(temp_wav, "rb") as audio_file:
            files = {
                "file": ("audio.wav", audio_file, "audio/wav")
            }
            headers = {
                "xi-api-key": ELEVENLABS_API_KEY
            }
            data = {
                "model_id": "scribe_v2",  # Используем лучшую модель
                "language_code": "en",    # Английский язык
                "diarize": "false",       # Не нужно разделять говорящих
                "tag_audio_events": "false"  # Экономим токены
            }
            
            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
        
        # Очищаем временные файлы
        os.unlink(temp_ogg)
        os.unlink(temp_wav)
        
        if response.status_code == 200:
            result = response.json()
            # Извлекаем текст из ответа Scribe
            text = result.get("text", "")
            if text:
                print(f"ElevenLabs Scribe recognized: '{text}'")
                return text
            else:
                print(f"Empty response from ElevenLabs")
                return ""
        else:
            print(f"ElevenLabs API error: {response.status_code} - {response.text}")
            return ""
            
    except requests.exceptions.Timeout:
        print("ElevenLabs API timeout")
        return ""
    except Exception as e:
        print(f"ElevenLabs STT error: {e}")
        return ""