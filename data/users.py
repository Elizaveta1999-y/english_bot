# data/users.py
import os
import json
import redis

# Подключение к Redis
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL not set in environment variables")

r = redis.from_url(REDIS_URL, decode_responses=True)

# Префикс для ключей, чтобы не конфликтовать с другими приложениями
PREFIX = "user_state:"

def get_user_state(user_id: int) -> dict:
    """Возвращает состояние пользователя из Redis."""
    key = f"{PREFIX}{user_id}"
    data = r.get(key)
    if data:
        return json.loads(data)
    return {}

def set_user_state(user_id: int, data: dict):
    """Сохраняет состояние пользователя в Redis."""
    key = f"{PREFIX}{user_id}"
    r.set(key, json.dumps(data))

def set_user_name(user_id: int, name: str):
    state = get_user_state(user_id)
    state["name"] = name
    set_user_state(user_id, state)

def set_user_level(user_id: int, level: str):
    state = get_user_state(user_id)
    state["level"] = level
    set_user_state(user_id, state)

def set_user_mode(user_id: int, mode: str):
    state = get_user_state(user_id)
    state["mode"] = mode
    set_user_state(user_id, state)

def get_user_history(user_id: int):
    state = get_user_state(user_id)
    return state.get("history", [])

def add_to_history(user_id: int, role: str, text: str, max_length: int = 20):
    state = get_user_state(user_id)
    history = state.get("history", [])
    history.append({"role": role, "text": text})
    if len(history) > max_length:
        history = history[-max_length:]
    state["history"] = history
    set_user_state(user_id, state)