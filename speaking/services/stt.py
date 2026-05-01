import os
import tempfile
import subprocess
import wave
import json
import urllib.request
import zipfile
from vosk import Model, KaldiRecognizer

_model = None

def download_vosk_model():
    model_dir = "models"
    model_name = "vosk-model-small-en-us-0.15"
    model_path = os.path.join(model_dir, model_name)
    
    if os.path.exists(model_path):
        return model_path
    
    os.makedirs(model_dir, exist_ok=True)
    zip_path = os.path.join(model_dir, f"{model_name}.zip")
    url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
    
    print(f"Downloading Vosk model...")
    urllib.request.urlretrieve(url, zip_path)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(model_dir)
    
    os.remove(zip_path)
    print("Vosk model ready")
    return model_path

def get_model():
    global _model
    if _model is None:
        model_path = download_vosk_model()
        _model = Model(model_path)
        print("Vosk model loaded")
    return _model

async def voice_to_text(file_bytes: bytes) -> str:
    temp_ogg = None
    temp_wav = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_ogg = f.name
        
        temp_wav = tempfile.mktemp(suffix=".wav")
        subprocess.run([
            "ffmpeg", "-i", temp_ogg,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            temp_wav, "-y"
        ], check=True, capture_output=True)
        
        model = get_model()
        wf = wave.open(temp_wav, "rb")
        rec = KaldiRecognizer(model, wf.getframerate())
        
        texts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                if 'text' in res:
                    texts.append(res['text'])
        
        final = json.loads(rec.FinalResult())
        if 'text' in final:
            texts.append(final['text'])
        
        wf.close()
        os.unlink(temp_ogg)
        os.unlink(temp_wav)
        
        result = " ".join(texts).strip()
        print(f"Vosk recognized: '{result}'")
        return result
    except Exception as e:
        print(f"Vosk STT error: {e}")
        return ""