import json
import os
import aiofiles
from typing import List, Dict, Any

USERS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")

async def _ensure_table():
    """Создаёт файл users.json, если его нет."""
    if not os.path.exists(USERS_FILE):
        async with aiofiles.open(USERS_FILE, 'w', encoding='utf-8') as f:
            await f.write('{}')

async def get_user_state(user_id: int) -> dict:
    """Возвращает состояние пользователя (словарь)."""
    await _ensure_table()
    async with aiofiles.open(USERS_FILE, 'r', encoding='utf-8') as f:
        content = await f.read()
        data = json.loads(content)
    return data.get(str(user_id), {})

async def set_user_state(user_id: int, state: dict):
    """Сохраняет состояние пользователя."""
    await _ensure_table()
    async with aiofiles.open(USERS_FILE, 'r', encoding='utf-8') as f:
        content = await f.read()
        data = json.loads(content)
    data[str(user_id)] = state
    async with aiofiles.open(USERS_FILE, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, indent=2, ensure_ascii=False))

async def add_to_history(user_id: int, role: str, content: str):
    """Добавляет сообщение в историю диалога пользователя."""
    state = await get_user_state(user_id)
    if 'history' not in state:
        state['history'] = []
    state['history'].append({'role': role, 'content': content})
    await set_user_state(user_id, state)