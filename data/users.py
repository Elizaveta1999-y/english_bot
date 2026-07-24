import os
import json
import asyncio
from utils.db import get_connection

# ---------- Вспомогательная функция для создания таблицы ----------
def _ensure_table():
    """Создаёт таблицу user_states, если её нет."""
    async def _create():
        conn = await get_connection()
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id BIGINT PRIMARY KEY,
                state JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
        await conn.close()
    asyncio.run(_create())

# ---------- Основные функции ----------
def get_user_state(user_id: int) -> dict:
    """Возвращает состояние пользователя из PostgreSQL."""
    _ensure_table()
    async def _get():
        conn = await get_connection()
        row = await conn.fetchrow("SELECT state FROM user_states WHERE user_id = $1", user_id)
        await conn.close()
        if row:
            return row["state"]
        return {}
    return asyncio.run(_get())

def set_user_state(user_id: int, data: dict):
    """Сохраняет состояние пользователя в PostgreSQL."""
    _ensure_table()
    async def _set():
        conn = await get_connection()
        await conn.execute("""
            INSERT INTO user_states (user_id, state)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (user_id) DO UPDATE SET state = $2::jsonb
        """, user_id, json.dumps(data))
        await conn.close()
    asyncio.run(_set())

# ---------- Дополнительные удобные функции ----------
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