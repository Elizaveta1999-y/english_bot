import os
import json
import logging
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool as pg_pool

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

VOICE_LIMIT_SECONDS = 5 * 3600  # 5 часов — лимит голосового общения в месяц

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


def is_voice_limit_reached(user_id: int) -> bool:
    """
    True, если лимит голоса (5 ч/мес) достигнут ИЛИ подписка истекла/отсутствует.
    """
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT subscription_until, COALESCE(total_voice_seconds_month, 0) FROM users WHERE user_id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            if row is None:
                return True
            sub_until = row[0] or 0
            used = row[1] or 0
            now_ts = int(datetime.now().timestamp())
            if sub_until <= now_ts:
                return True
            return used >= VOICE_LIMIT_SECONDS
    finally:
        _get_pool().putconn(conn)


def add_voice_seconds(user_id: int, seconds: int, mode: str):
    """
    Прибавляет секунды голоса в счётчик, только если подписка активна.
    mode: 'speaking' или 'roleplay'.
    Если подписка истекла — сбрасывает все голосовые счётчики в 0.
    """
    if mode not in ("speaking", "roleplay"):
        return
    if not seconds or seconds <= 0:
        return

    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT subscription_until FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                return
            sub_until = row[0] or 0
            now_ts = int(datetime.now().timestamp())

            if sub_until <= now_ts:
                cur.execute("""
                    UPDATE users
                    SET speaking_seconds_month = 0,
                        roleplay_seconds_month = 0,
                        total_voice_seconds_month = 0
                    WHERE user_id = %s
                """, (user_id,))
            else:
                if mode == "speaking":
                    cur.execute("""
                        UPDATE users
                        SET speaking_seconds_month = COALESCE(speaking_seconds_month, 0) + %s,
                            total_voice_seconds_month = COALESCE(total_voice_seconds_month, 0) + %s
                        WHERE user_id = %s
                    """, (seconds, seconds, user_id))
                else:
                    cur.execute("""
                        UPDATE users
                        SET roleplay_seconds_month = COALESCE(roleplay_seconds_month, 0) + %s,
                            total_voice_seconds_month = COALESCE(total_voice_seconds_month, 0) + %s
                        WHERE user_id = %s
                    """, (seconds, seconds, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка add_voice_seconds({user_id}, {mode}, {seconds}): {e}")
    finally:
        _get_pool().putconn(conn)


def add_to_history(user_id: int, role: str, content: str):
    state = get_user_state(user_id)
    mode = state.get('mode', 'general')
    history_key = f"{mode}_history"
    if history_key not in state:
        state[history_key] = []
    state[history_key].append({'role': role, 'content': content})
    set_user_state(user_id, state)


def get_user_history(user_id: int, mode: str = None) -> list:
    state = get_user_state(user_id)
    if mode is None:
        mode = state.get('mode', 'general')
    history_key = f"{mode}_history"
    return state.get(history_key, [])


def clear_user_history(user_id: int, mode: str = None):
    state = get_user_state(user_id)
    if mode is None:
        mode = state.get('mode', 'general')
    history_key = f"{mode}_history"
    if history_key in state:
        state[history_key] = []
        set_user_state(user_id, state)


def set_user_mode(user_id: int, mode: str):
    state = get_user_state(user_id)
    state['mode'] = mode
    set_user_state(user_id, state)


def get_user_mode(user_id: int) -> str:
    state = get_user_state(user_id)
    return state.get('mode', '')