import json
import os

USERS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")

def _ensure_table():
    """Создаёт файл users.json, если его нет."""
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

def get_user_state(user_id: int) -> dict:
    """Возвращает состояние пользователя (словарь)."""
    _ensure_table()
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get(str(user_id), {})

def set_user_state(user_id: int, state: dict):
    """Сохраняет состояние пользователя."""
    _ensure_table()
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data[str(user_id)] = state
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def add_to_history(user_id: int, role: str, content: str):
    """
    Добавляет сообщение в историю, соответствующую текущему режиму пользователя.
    Режим определяется из поля 'mode' в состоянии пользователя.
    Если режим не задан, используется ключ 'history'.
    """
    state = get_user_state(user_id)
    mode = state.get('mode', 'general')
    history_key = f"{mode}_history"
    if history_key not in state:
        state[history_key] = []
    state[history_key].append({'role': role, 'content': content})
    set_user_state(user_id, state)

def get_user_history(user_id: int, mode: str = None) -> list:
    """
    Возвращает историю для указанного режима.
    Если mode не указан, используется текущий режим из состояния.
    Если режим не задан, возвращается история по ключу 'history'.
    """
    state = get_user_state(user_id)
    if mode is None:
        mode = state.get('mode', 'general')
    history_key = f"{mode}_history"
    return state.get(history_key, [])

def clear_user_history(user_id: int, mode: str = None):
    """
    Очищает историю для указанного режима.
    Если mode не указан, используется текущий режим из состояния.
    """
    state = get_user_state(user_id)
    if mode is None:
        mode = state.get('mode', 'general')
    history_key = f"{mode}_history"
    if history_key in state:
        state[history_key] = []
        set_user_state(user_id, state)

def set_user_mode(user_id: int, mode: str):
    """Устанавливает текущий режим пользователя (например, 'speaking', 'roleplay')."""
    state = get_user_state(user_id)
    state['mode'] = mode
    set_user_state(user_id, state)

def get_user_mode(user_id: int) -> str:
    """Возвращает текущий режим пользователя."""
    state = get_user_state(user_id)
    return state.get('mode', '')