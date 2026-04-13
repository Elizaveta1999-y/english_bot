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


def set_user_mode(user_id: int, mode: str):
    if user_id not in users:
        users[user_id] = {}

    users[user_id]["mode"] = mode