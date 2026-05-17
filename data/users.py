# data/users.py
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

def get_user_level(user_id: int) -> str:
    return users.get(user_id, {}).get("level", None)  # None если ещё не выбран

def set_user_mode(user_id: int, mode: str):
    if user_id not in users:
        users[user_id] = {}
    users[user_id]["mode"] = mode

def get_user_history(user_id: int):
    if user_id not in users:
        users[user_id] = {}
    if "history" not in users[user_id]:
        users[user_id]["history"] = []
    return users[user_id]["history"]

def add_to_history(user_id: int, role: str, text: str, max_length: int = 20):
    history = get_user_history(user_id)
    history.append({"role": role, "text": text})
    if len(history) > max_length:
        history.pop(0)