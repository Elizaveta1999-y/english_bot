# data/users.py
# Простое хранилище в памяти (MVP)
# Позже заменим на Redis или БД

users = {}

def get_user_state(user_id: int):
    return users.get(user_id, {})

def set_user_state(user_id: int, data: dict):
    users[user_id] = data

def set_user_name(user_id: int, name: str):
    if user_id not in users:
        users[user_id] = {}
    users[user_id]["name"] = name

def set_user_level(user_id: int, level: str):
    if user_id not in users:
        users[user_id] = {}
    users[user_id]["level"] = level

def set_user_mode(user_id: int, mode: str):
    if user_id not in users:
        users[user_id] = {}
    users[user_id]["mode"] = mode

def get_user_history(user_id: int):
    if user_id not in users:
        users[user_id] = {}
    if "history" not in users[user_id]:
        users[user_id]["history"] = []  # каждый элемент: {"role": "user/assistant", "text": "..."}
    return users[user_id]["history"]

def add_to_history(user_id: int, role: str, text: str, max_length: int = 10):
    """Добавляет сообщение в историю."""
    history = get_user_history(user_id)
    history.append({"role": role, "text": text})
    # оставляем только последние max_length сообщений
    if len(history) > max_length:
        history.pop(0)