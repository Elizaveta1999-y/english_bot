import os
import json
import logging

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool as pg_pool

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Render иногда отдаёт старую схему "postgres://" — psycopg2 её не понимает
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connection_pool = None
_table_ready = False


def _get_pool():
    global _connection_pool
    if _connection_pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _connection_pool = pg_pool.ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _connection_pool


def _ensure_table():
    """Создаёт таблицу users (если её нет) и добавляет колонку state."""
    global _table_ready
    if _table_ready:
        return
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    registered_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                    last_active BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
                    state JSONB DEFAULT '{}'::jsonb
                )
            """)
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS state JSONB DEFAULT '{}'::jsonb")
        conn.commit()
        _table_ready = True
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка при создании/обновлении таблицы: {e}")
        raise
    finally:
        _get_pool().putconn(conn)


def get_user_state(user_id: int) -> dict:
    """Возвращает состояние пользователя (словарь) из Postgres."""
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT state FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row and row["state"]:
                return dict(row["state"])
            return {}
    finally:
        _get_pool().putconn(conn)


def set_user_state(user_id: int, state: dict):
    """Сохраняет состояние пользователя в Postgres (создаёт запись при необходимости)."""
    _ensure_table()
    state_json = json.dumps(state, ensure_ascii=False)
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, state, registered_at, last_active)
                VALUES (%s, %s::jsonb,
                        EXTRACT(EPOCH FROM NOW())::BIGINT,
                        EXTRACT(EPOCH FROM NOW())::BIGINT)
                ON CONFLICT (user_id) DO UPDATE
                    SET state = EXCLUDED.state,
                        last_active = EXTRACT(EPOCH FROM NOW())::BIGINT
            """, (user_id, state_json))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка set_user_state({user_id}): {e}")
    finally:
        _get_pool().putconn(conn)


async def get_or_create_user(user_id: int, username: str = None,
                             first_name: str = None, last_name: str = None) -> dict:
    """
    Создаёт пользователя в Postgres, если его нет, и обновляет профиль
    (username, first_name, last_name, last_active). Возвращает state.
    Оставлено async, потому что в start.py вызывается через await.
    """
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO users (user_id, username, first_name, last_name,
                                   registered_at, last_active)
                VALUES (%s, %s, %s, %s,
                        EXTRACT(EPOCH FROM NOW())::BIGINT,
                        EXTRACT(EPOCH FROM NOW())::BIGINT)
                ON CONFLICT (user_id) DO UPDATE
                    SET username    = COALESCE(EXCLUDED.username,   users.username),
                        first_name  = COALESCE(EXCLUDED.first_name, users.first_name),
                        last_name   = COALESCE(EXCLUDED.last_name,  users.last_name),
                        last_active = EXTRACT(EPOCH FROM NOW())::BIGINT
                RETURNING state
            """, (user_id, username, first_name, last_name))
            row = cur.fetchone()
        conn.commit()
        if row and row["state"]:
            return dict(row["state"])
        return {}
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка get_or_create_user({user_id}): {e}")
        return {}
    finally:
        _get_pool().putconn(conn)


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