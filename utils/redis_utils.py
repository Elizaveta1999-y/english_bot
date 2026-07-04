import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def get_global_welcome_index():
    """Получить глобальный индекс приветственного сообщения (0-4)."""
    idx = r.get("reading_welcome_global_index")
    if idx is None:
        idx = 0
        r.set("reading_welcome_global_index", idx)
    return int(idx)

def increment_global_welcome_index():
    """Увеличить глобальный индекс, после 4 сбросить на 0."""
    idx = get_global_welcome_index()
    idx = (idx + 1) % 5
    r.set("reading_welcome_global_index", idx)
    return idx

def get_user_progress(user_id: int, type_key: str, level_key: str):
    """Получить текущий индекс задания для пользователя."""
    key = f"reading_progress:{user_id}:{type_key}:{level_key}"
    val = r.get(key)
    if val is None:
        return 0
    return int(val)

def set_user_progress(user_id: int, type_key: str, level_key: str, index: int):
    """Установить индекс задания."""
    key = f"reading_progress:{user_id}:{type_key}:{level_key}"
    r.set(key, index)

def get_user_stats(user_id: int, type_key: str, level_key: str):
    """Получить статистику (правильно, ошибок)."""
    correct_key = f"reading_correct:{user_id}:{type_key}:{level_key}"
    wrong_key = f"reading_wrong:{user_id}:{type_key}:{level_key}"
    correct = int(r.get(correct_key) or 0)
    wrong = int(r.get(wrong_key) or 0)
    return correct, wrong

def update_user_stats(user_id: int, type_key: str, level_key: str, correct: bool):
    """Обновить статистику: увеличить correct или wrong."""
    if correct:
        key = f"reading_correct:{user_id}:{type_key}:{level_key}"
    else:
        key = f"reading_wrong:{user_id}:{type_key}:{level_key}"
    r.incr(key)

def reset_user_progress(user_id: int, type_key: str, level_key: str):
    """Сбросить прогресс и статистику для данного типа/уровня."""
    r.delete(f"reading_progress:{user_id}:{type_key}:{level_key}")
    r.delete(f"reading_correct:{user_id}:{type_key}:{level_key}")
    r.delete(f"reading_wrong:{user_id}:{type_key}:{level_key}")