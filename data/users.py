# data/users.py
users = {}

def get_user_state(user_id: int):
    if user_id not in users:
        users[user_id] = {}  # всегда возвращаем словарь, а не set
    return users[user_id]

def set_user_state(user_id: int, data: dict):
    users[user_id] = data

def set_user_name(user_id: int, name: str):
    state = get_user_state(user_id)
    state["name"] = name

def set_user_level(user_id: int, level: str):
    state = get_user_state(user_id)
    state["level"] = level

def set_user_mode(user_id: int, mode: str):
    state = get_user_state(user_id)
    state["mode"] = mode

def get_user_history(user_id: int):
    state = get_user_state(user_id)
    if "history" not in state:
        state["history"] = []
    return state["history"]

def add_to_history(user_id: int, role: str, text: str, max_length: int = 20):
    history = get_user_history(user_id)
    history.append({"role": role, "text": text})
    if len(history) > max_length:
        history.pop(0)