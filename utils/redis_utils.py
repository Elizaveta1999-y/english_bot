import os
import redis

# Переменные окружения (должны быть заданы на Render)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# Создаём подключение с параметрами
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=5,   # таймаут, чтобы не висеть
    socket_timeout=5
)

# --- Ваши существующие функции (без изменений) ---

def get_global_welcome_index():
    idx = r.get("reading_welcome_global_index")
    if idx is None:
        idx = 0
        r.set("reading_welcome_global_index", idx)
    return int(idx)

def increment_global_welcome_index():
    idx = get_global_welcome_index()
    idx = (idx + 1) % 5
    r.set("reading_welcome_global_index", idx)
    return idx

def get_user_progress(user_id: int, type_key: str, level_key: str):
    key = f"reading_progress:{user_id}:{type_key}:{level_key}"
    val = r.get(key)
    if val is None:
        return 0
    return int(val)

def set_user_progress(user_id: int, type_key: str, level_key: str, index: int):
    key = f"reading_progress:{user_id}:{type_key}:{level_key}"
    r.set(key, index)

def get_user_stats(user_id: int, type_key: str, level_key: str):
    correct_key = f"reading_correct:{user_id}:{type_key}:{level_key}"
    wrong_key = f"reading_wrong:{user_id}:{type_key}:{level_key}"
    correct = int(r.get(correct_key) or 0)
    wrong = int(r.get(wrong_key) or 0)
    return correct, wrong

def update_user_stats(user_id: int, type_key: str, level_key: str, correct: bool):
    if correct:
        key = f"reading_correct:{user_id}:{type_key}:{level_key}"
    else:
        key = f"reading_wrong:{user_id}:{type_key}:{level_key}"
    r.incr(key)

def reset_user_progress(user_id: int, type_key: str, level_key: str):
    r.delete(f"reading_progress:{user_id}:{type_key}:{level_key}")
    r.delete(f"reading_correct:{user_id}:{type_key}:{level_key}")
    r.delete(f"reading_wrong:{user_id}:{type_key}:{level_key}")