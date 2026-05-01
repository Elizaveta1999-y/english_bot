import os
import tempfile
import subprocess
import urllib.request
import platform
import stat
import zipfile

# Глобальные пути к бинарнику и модели (скачиваются один раз)
WHISPER_BIN = None
WHISPER_MODEL = None

def download_whisper():
    """Скачивает скомпилированный whisper.cpp для Linux"""
    global WHISPER_BIN
    if WHISPER_BIN and os.path.exists(WHISPER_BIN):
        return WHISPER_BIN
    
    # Создаём папку для инструментов
    tools_dir = "whisper_tools"
    os.makedirs(tools_dir, exist_ok=True)
    
    # Определяем архитектуру (Render использует Linux x86_64)
    system = platform.system()
    arch = platform.machine()
    
    if system != "Linux" or arch != "x86_64":
        print(f"Warning: Unexpected platform {system} {arch}, but trying anyway...")
    
    # URL к скомпилированному бинарнику whisper-cli (из официального репозитория)
    # Используем предварительно скомпилированную версию для Linux
    whisper_bin_url = "https://github.com/ggerganov/whisper.cpp/releases/download/v1.7.0/whisper-cli"
    whisper_bin_path = os.path.join(tools_dir, "whisper-cli")
    
    if not os.path.exists(whisper_bin_path):
        print("Downloading whisper-cli binary...")
        urllib.request.urlretrieve(whisper_bin_url, whisper_bin_path)
        # Делаем исполняемым
        st = os.stat(whisper_bin_path)
        os.chmod(whisper_bin_path, st.st_mode | stat.S_IEXEC)
        print("whisper-cli downloaded and made executable.")
    
    WHISPER_BIN = whisper_bin_path
    return WHISPER_BIN

def download_model():
    """Скачивает tiny.en модель (около 40 МБ)"""
    global WHISPER_MODEL
    if WHISPER_MODEL and os.path.exists(WHISPER_MODEL):
        return WHISPER_MODEL
    
    models_dir = "whisper_models"
    os.makedirs(models_dir, exist_ok=True)
    
    model_name = "ggml-tiny.en.bin"
    model_url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_name}"
    model_path = os.path.join(models_dir, model_name)
    
    if not os.path.exists(model_path):
        print(f"Downloading model {model_name}...")
        urllib.request.urlretrieve(model_url, model_path)
        print("Model downloaded.")
    
    WHISPER_MODEL = model_path
    return WHISPER_MODEL

async def voice_to_text(file_bytes: bytes) -> str:
    """Распознаёт речь через whisper.cpp"""
    temp_audio = None
    try:
        # Сохраняем голосовое во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(file_bytes)
            temp_audio = f.name
        
        # Проверяем, что whisper уже скачан
        whisper_bin = download_whisper()
        model_path = download_model()
        
        # Конвертируем OGG в WAV через pydub (не требует FFmpeg на уровне системы)
        from pydub import AudioSegment
        temp_wav = tempfile.mktemp(suffix=".wav")
        audio = AudioSegment.from_ogg(temp_audio)
        audio.export(temp_wav, format="wav")
        
        # Вызываем whisper-cli для распознавания
        cmd = [
            whisper_bin,
            "-m", model_path,
            "-f", temp_wav,
            "-l", "en",
            "--no-prints",
            "--output-txt"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # whisper-cli выводит результат в stderr или в файл. Парсим вывод
        output = result.stderr if result.stderr else result.stdout
        
        # Пробуем извлечь распознанный текст
        lines = output.split('\n')
        text_parts = []
        for line in lines:
            if line.strip() and not line.startswith('whisper') and not line.startswith('['):
                text_parts.append(line.strip())
        
        recognized = ' '.join(text_parts).strip()
        
        # Очистка
        os.unlink(temp_audio)
        os.unlink(temp_wav)
        
        if not recognized:
            print(f"Whisper raw output: {output[:200]}")
            return ""
        
        print(f"Whisper recognized: '{recognized}'")
        return recognized
        
    except subprocess.TimeoutExpired:
        print("Whisper timeout")
        return ""
    except Exception as e:
        print(f"Whisper STT error: {e}")
        return ""