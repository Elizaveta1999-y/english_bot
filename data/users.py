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

# ---------- ЛИМИТЫ ----------
VOICE_LIMIT_SECONDS = 9000          # 2.5 часа = 9000 секунд
TRIAL_DURATION_SECONDS = 48 * 3600  # 48 часов
TRIAL_VOICE_LIMIT = 4               # голосовых в триале (speaking + roleplay)
TRIAL_WRITING_LIMIT = 2             # фидбеков в письме
TRIAL_GOVORENIE_LIMIT = 2           # фидбеков в говорении

ACCESS_UNLIMITED = "unlimited"
ACCESS_SUBSCRIBED = "subscribed"
ACCESS_TRIAL = "trial"
ACCESS_FREE = "free"

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
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_until BIGINT DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_started BIGINT DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_until BIGINT DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS total_voice_seconds_month BIGINT DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS speaking_seconds_month BIGINT DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roleplay_seconds_month BIGINT DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_voice_count INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_writing_count INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_govorenie_count INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_unlimited BOOLEAN DEFAULT FALSE")
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


# ========== ТРИАЛ И ПОДПИСКА ==========
def start_trial_if_needed(user_id: int):
    """Активирует триал при первом /start. Если trial_started > 0 — ничего не делает."""
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT trial_started FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                return
            trial_started = row[0] or 0
            if trial_started > 0:
                return
            now_ts = int(datetime.now().timestamp())
            trial_until = now_ts + TRIAL_DURATION_SECONDS
            cur.execute("""
                UPDATE users
                SET trial_started = %s, trial_until = %s
                WHERE user_id = %s
            """, (now_ts, trial_until, user_id))
        conn.commit()
        logger.info(f"[users] Триал активирован для {user_id} до {trial_until}")
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка start_trial_if_needed({user_id}): {e}")
    finally:
        _get_pool().putconn(conn)


def is_trial_active(user_id: int) -> bool:
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT trial_started, trial_until FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                return False
            trial_started = row[0] or 0
            trial_until = row[1] or 0
            now_ts = int(datetime.now().timestamp())
            return trial_started > 0 and trial_until > now_ts
    finally:
        _get_pool().putconn(conn)


def is_subscribed(user_id: int) -> bool:
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT subscription_until FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row is None:
                return False
            sub_until = row[0] or 0
            now_ts = int(datetime.now().timestamp())
            return sub_until > now_ts
    finally:
        _get_pool().putconn(conn)


def is_unlimited(user_id: int) -> bool:
    _ensure_table()
    admin_id = int(os.getenv("ADMIN_ID", 0) or 0)
    if admin_id and user_id == admin_id:
        return True
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_unlimited FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return bool(row and row[0])
    finally:
        _get_pool().putconn(conn)


def get_user_access_level(user_id: int) -> str:
    """'unlimited' | 'subscribed' | 'trial' | 'free'"""
    if is_unlimited(user_id):
        return ACCESS_UNLIMITED
    if is_subscribed(user_id):
        return ACCESS_SUBSCRIBED
    if is_trial_active(user_id):
        return ACCESS_TRIAL
    return ACCESS_FREE


# ========== СЧЁТЧИКИ ТРИАЛА ==========
def get_trial_voice_count(user_id: int) -> int:
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(trial_voice_count, 0) FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        _get_pool().putconn(conn)


def increment_trial_voice(user_id: int):
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET trial_voice_count = COALESCE(trial_voice_count, 0) + 1
                WHERE user_id = %s
            """, (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка increment_trial_voice({user_id}): {e}")
    finally:
        _get_pool().putconn(conn)


def get_trial_writing_count(user_id: int) -> int:
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(trial_writing_count, 0) FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        _get_pool().putconn(conn)


def increment_trial_writing(user_id: int):
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET trial_writing_count = COALESCE(trial_writing_count, 0) + 1
                WHERE user_id = %s
            """, (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка increment_trial_writing({user_id}): {e}")
    finally:
        _get_pool().putconn(conn)


def get_trial_govorenie_count(user_id: int) -> int:
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(trial_govorenie_count, 0) FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        _get_pool().putconn(conn)


def increment_trial_govorenie(user_id: int):
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET trial_govorenie_count = COALESCE(trial_govorenie_count, 0) + 1
                WHERE user_id = %s
            """, (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"[users] Ошибка increment_trial_govorenie({user_id}): {e}")
    finally:
        _get_pool().putconn(conn)


# ========== ПРОВЕРКИ ДЛЯ ХЕНДЛЕРОВ ==========
def check_voice_access(user_id: int) -> tuple:
    """
    Returns (allowed, reason).
    reason: "ok" | "trial_voice_limit" | "free_no_access" | "sub_voice_limit"
    """
    level = get_user_access_level(user_id)

    if level == ACCESS_UNLIMITED:
        return (True, "ok")

    if level == ACCESS_SUBSCRIBED:
        if is_voice_limit_reached(user_id):
            return (False, "sub_voice_limit")
        return (True, "ok")

    if level == ACCESS_TRIAL:
        if get_trial_voice_count(user_id) >= TRIAL_VOICE_LIMIT:
            return (False, "trial_voice_limit")
        return (True, "ok")

    return (False, "free_no_access")


def check_writing_access(user_id: int) -> tuple:
    """
    Returns (allowed, reason).
    reason: "ok" | "trial_writing_limit" | "free_no_access"
    """
    level = get_user_access_level(user_id)

    if level in (ACCESS_UNLIMITED, ACCESS_SUBSCRIBED):
        return (True, "ok")

    if level == ACCESS_TRIAL:
        if get_trial_writing_count(user_id) >= TRIAL_WRITING_LIMIT:
            return (False, "trial_writing_limit")
        return (True, "ok")

    return (False, "free_no_access")


def check_govorenie_access(user_id: int) -> tuple:
    """
    Returns (allowed, reason).
    reason: "ok" | "trial_govorenie_limit" | "free_no_access"
    """
    level = get_user_access_level(user_id)

    if level in (ACCESS_UNLIMITED, ACCESS_SUBSCRIBED):
        return (True, "ok")

    if level == ACCESS_TRIAL:
        if get_trial_govorenie_count(user_id) >= TRIAL_GOVORENIE_LIMIT:
            return (False, "trial_govorenie_limit")
        return (True, "ok")

    return (False, "free_no_access")


# ========== ГОЛОСОВЫЕ СЕКУНДЫ (подписка) ==========
def is_voice_limit_reached(user_id: int) -> bool:
    """True, если 2.5 ч/мес исчерпаны. НЕ проверяет подписку."""
    _ensure_table()
    conn = _get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(total_voice_seconds_month, 0) FROM users WHERE user_id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            if row is None:
                return False
            return (row[0] or 0) >= VOICE_LIMIT_SECONDS
    finally:
        _get_pool().putconn(conn)


def add_voice_seconds(user_id: int, seconds: int, mode: str):
    """Прибавляет секунды. Для подписчиков. Для триала — increment_trial_voice."""
    if mode not in ("speaking", "roleplay") or not seconds or seconds <= 0:
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


# ========== ИСТОРИЯ / РЕЖИМ ==========
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
    return state.get(f"{mode}_history", [])


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
    return get_user_state(user_id).get('mode', '')