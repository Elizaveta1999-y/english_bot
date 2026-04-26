import os
import tempfile
import subprocess
import wave
import json
import urllib.request
import zipfile
from vosk import Model, KaldiRecognizer

# Глобальная переменная для модели
_model = None

def download_vosk_model():
    """Скачивает и распаковывает Vosk модель (small english) в папку models."""
    model_dir = "models"
    model_name = "vosk-model-small-en-us-0.15"
    model_path = os.path.join(model_dir, model_name)
    
    if os.path.exists(model_path):
        print(f"Model already exists at {model_path}")
        return model_path
    
    os.makedirs(model_dir, exist_ok=True)
    zip_path = os.path.join(model_dir, f"{model_name}.zip")
    url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
    
    print(f"Downloading Vosk model from {url} ...")
    urllib.request.urlretrieve(url, zip_path)
    
    print("Extracting model...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(model_dir)
    
    os.remove(zip_path)
    print("Model downloaded and extracted.")
    return model_path

def get_model():
    global _model
    if _model is None:
        model_path = download_vosk_model()
        print(f"Loading Vosk model from {model_path}...")
        _model = Model(model_path)
        print("Vosk model loaded.")
    return _model

async def voice_to_text(file_bytes: bytes) -> str:
    """Распознаёт речь через Vosk (бесплатно, офлайн)."""
    temp_ogg = None
    temp_wav = None
    try:
        # Сохраняем входной OGG файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_ogg = f.name
        
        # Конвертируем в WAV (16 kHz, mono, PCM)
        temp_wav = tempfile.mktemp(suffix=".wav")
        cmd = [
            "ffmpeg", "-i", temp_ogg, 
            "-acodec", "pcm_s16le", 
            "-ar", "16000", 
            "-ac", "1", 
            temp_wav, "-y"
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Распознаём с помощью Vosk
        model = get_model()
        wf = wave.open(temp_wav, "rb")
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(False)
        
        texts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                if 'text' in res and res['text']:
                    texts.append(res['text'])
        
        # Финальный результат
        final = json.loads(rec.FinalResult())
        if 'text' in final and final['text']:
            texts.append(final['text'])
        
        wf.close()
        
        # Очистка
        os.unlink(temp_ogg)
        os.unlink(temp_wav)
        
        recognized = " ".join(texts).strip()
        print(f"Vosk recognized: '{recognized}'")
        return recognized
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
        return ""
    except Exception as e:
        print(f"Vosk STT error: {e}")
        return ""