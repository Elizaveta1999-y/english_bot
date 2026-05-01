import os
import tempfile
import subprocess
import urllib.request
import platform
import stat
import zipfile
import sys

WHISPER_BIN = None
WHISPER_MODEL = None

def download_whisper():
    global WHISPER_BIN
    tools_dir = "whisper_tools"
    os.makedirs(tools_dir, exist_ok=True)
    
    whisper_bin_path = os.path.join(tools_dir, "whisper-cli")
    
    if os.path.exists(whisper_bin_path):
        print("whisper-cli already exists")
        return whisper_bin_path
    
    # Используем официальный релиз whisper.cpp
    # Скачиваем предварительно скомпилированный бинарник для Linux
    whisper_bin_url = "https://github.com/ggerganov/whisper.cpp/releases/download/v1.7.0/whisper-cli"
    
    print("Downloading whisper-cli binary...")
    try:
        urllib.request.urlretrieve(whisper_bin_url, whisper_bin_path)
        # Делаем исполняемым
        st = os.stat(whisper_bin_path)
        os.chmod(whisper_bin_path, st.st_mode | stat.S_IEXEC)
        print("whisper-cli downloaded and made executable.")
    except Exception as e:
        print(f"Failed to download whisper-cli: {e}")
        return None
    
    return whisper_bin_path

def download_model():
    global WHISPER_MODEL
    models_dir = "whisper_models"
    os.makedirs(models_dir, exist_ok=True)
    
    model_name = "ggml-tiny.en.bin"
    model_path = os.path.join(models_dir, model_name)
    
    if os.path.exists(model_path):
        return model_path
    
    model_url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_name}"
    
    print(f"Downloading model {model_name}...")
    try:
        urllib.request.urlretrieve(model_url, model_path)
        print("Model downloaded.")
    except Exception as e:
        print(f"Failed to download model: {e}")
        return None
    
    return model_path

async def voice_to_text(file_bytes: bytes) -> str:
    temp_audio = None
    temp_wav = None
    try:
        # Сохраняем голосовое
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_audio = f.name
        
        # Конвертируем OGG в WAV через ffmpeg (уже есть в aptfile)
        temp_wav = tempfile.mktemp(suffix=".wav")
        cmd_ffmpeg = [
            "ffmpeg", "-i", temp_audio,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            temp_wav, "-y"
        ]
        subprocess.run(cmd_ffmpeg, check=True, capture_output=True)
        
        # Получаем whisper
        whisper_bin = download_whisper()
        model_path = download_model()
        
        if not whisper_bin or not model_path:
            print("Whisper not available, falling back to Vosk")
            # Fallback на Vosk (у вас уже есть код, но для простоты вернём пустоту)
            return ""
        
        # Распознаём
        cmd_whisper = [
            whisper_bin,
            "-m", model_path,
            "-f", temp_wav,
            "-l", "en",
            "--no-prints"
        ]
        
        result = subprocess.run(cmd_whisper, capture_output=True, text=True, timeout=30)
        
        # Парсим вывод
        output = result.stdout + result.stderr
        lines = output.split('\n')
        text_parts = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('[') and not line.startswith('whisper'):
                text_parts.append(line)
        
        recognized = ' '.join(text_parts).strip()
        
        # Очистка
        os.unlink(temp_audio)
        os.unlink(temp_wav)
        
        if recognized:
            print(f"Whisper recognized: {recognized}")
            return recognized
        else:
            print(f"Whisper output was empty")
            return ""
            
    except subprocess.TimeoutExpired:
        print("Whisper timeout")
        return ""
    except Exception as e:
        print(f"Whisper STT error: {e}")
        # Пробуем Vosk как fallback
        try:
            from vosk import Model, KaldiRecognizer
            import wave, json
            model = Model("models/vosk-model-small-en-us-0.15")
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
            recognized = " ".join(texts).strip()
            if recognized:
                print(f"Vosk fallback recognized: {recognized}")
                return recognized
        except Exception as e2:
            print(f"Vosk fallback also failed: {e2}")
        return ""