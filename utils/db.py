import os
import asyncpg
from typing import Tuple, List, Optional

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_connection()
    # Таблица пользователей
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            subscription_end BIGINT DEFAULT 0,
            registered_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
            last_active BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
        )
    """)
    # Таблица прогресса для других режимов
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            user_id BIGINT NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, type_key, level_key)
        )
    """)
    # Таблица ошибок
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            user_id BIGINT NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            task_index INTEGER NOT NULL,
            PRIMARY KEY (user_id, type_key, level_key, task_index)
        )
    """)
    # Таблица для прогресса письма
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS writing_progress (
            user_id BIGINT NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            current_index INTEGER DEFAULT 0,
            total_answered INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            session_answered INTEGER DEFAULT 0,
            session_score INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, type_key, level_key)
        )
    """)
    # Таблица для прогресса грамматики
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS grammar_progress (
            user_id BIGINT NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            current_index INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, type_key, level_key)
        )
    """)
    # Таблица для прогресса говорения
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS govorenie_progress (
            user_id BIGINT NOT NULL,
            task_type TEXT NOT NULL,
            level TEXT NOT NULL,
            current_task_id INTEGER DEFAULT 0,
            total_answered INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            session_answered INTEGER DEFAULT 0,
            session_score INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, task_type, level)
        )
    """)
    # Новая таблица для индекса прогресса (универсальная)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS progress_index (
            user_id BIGINT NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            current_index INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, type_key, level_key)
        )
    """)
    # Новая таблица для случайного порядка
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS random_order (
            user_id BIGINT NOT NULL,
            level_key TEXT NOT NULL,
            order_data JSONB NOT NULL,
            PRIMARY KEY (user_id, level_key)
        )
    """)
    # Таблица для состояний пользователей (user_states)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            user_id BIGINT PRIMARY KEY,
            state JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    # ---- ДОБАВЛЕННЫЕ ТАБЛИЦЫ ДЛЯ АДМИНКИ И БОНУСОВ ----
    # Таблица настроек бота (для технических работ)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Таблица заблокированных пользователей
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS blocked_users (
            user_id BIGINT PRIMARY KEY
        )
    """)
    # Добавляем колонки для подписки, пробного периода и бонусов
    await conn.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS subscription_until BIGINT DEFAULT 0,
        ADD COLUMN IF NOT EXISTS trial_started BIGINT DEFAULT 0,
        ADD COLUMN IF NOT EXISTS trial_until BIGINT DEFAULT 0,
        ADD COLUMN IF NOT EXISTS total_voice_seconds_month BIGINT DEFAULT 0,
        ADD COLUMN IF NOT EXISTS voice_reset_month INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS bonus_notification BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS bonus_reason TEXT DEFAULT ''
    """)
    await conn.close()

# ---------- Пользователи ----------
async def get_or_create_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO users (user_id, username, first_name, last_name) VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT
    """, user_id, username, first_name, last_name)
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return dict(row) if row else None

# ---------- Прогресс (для других режимов) ----------
async def get_user_stats_db(user_id: int, type_key: str, level_key: str) -> Tuple[int, int]:
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT correct, wrong FROM progress WHERE user_id = $1 AND type_key = $2 AND level_key = $3",
        user_id, type_key, level_key
    )
    await conn.close()
    if row:
        return row["correct"], row["wrong"]
    return 0, 0

async def update_user_stats_db(user_id: int, type_key: str, level_key: str, correct: bool):
    conn = await get_connection()
    field = "correct" if correct else "wrong"
    await conn.execute(f"""
        INSERT INTO progress (user_id, type_key, level_key, correct, wrong)
        VALUES ($1, $2, $3, 0, 0)
        ON CONFLICT (user_id, type_key, level_key)
        DO UPDATE SET {field} = progress.{field} + 1
    """, user_id, type_key, level_key)
    await conn.close()

async def reset_user_stats_db(user_id: int, type_key: str, level_key: str):
    conn = await get_connection()
    await conn.execute(
        "DELETE FROM progress WHERE user_id = $1 AND type_key = $2 AND level_key = $3",
        user_id, type_key, level_key
    )
    await conn.close()

# ---------- Ошибки ----------
async def add_reading_error_db(user_id: int, type_key: str, level_key: str, task_index: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO errors (user_id, type_key, level_key, task_index)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, type_key, level_key, task_index) DO NOTHING
    """, user_id, type_key, level_key, task_index)
    await conn.close()

async def remove_reading_error_db(user_id: int, type_key: str, level_key: str, task_index: int):
    conn = await get_connection()
    await conn.execute(
        "DELETE FROM errors WHERE user_id = $1 AND type_key = $2 AND level_key = $3 AND task_index = $4",
        user_id, type_key, level_key, task_index
    )
    await conn.close()

async def get_reading_errors_db(user_id: int, type_key: str, level_key: str) -> List[int]:
    conn = await get_connection()
    rows = await conn.fetch(
        "SELECT task_index FROM errors WHERE user_id = $1 AND type_key = $2 AND level_key = $3",
        user_id, type_key, level_key
    )
    await conn.close()
    return [row["task_index"] for row in rows]

async def clear_reading_errors_db(user_id: int, type_key: str, level_key: str):
    conn = await get_connection()
    await conn.execute(
        "DELETE FROM errors WHERE user_id = $1 AND type_key = $2 AND level_key = $3",
        user_id, type_key, level_key
    )
    await conn.close()

async def reset_all_user_progress(user_id: int):
    conn = await get_connection()
    await conn.execute("DELETE FROM progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM errors WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM grammar_progress WHERE user_id = $1", user_id)
    await conn.close()

# ---------- Функции для письма ----------
async def get_writing_progress(user_id: int, type_key: str, level_key: str):
    conn = await get_connection()
    row = await conn.fetchrow(
        """SELECT current_index, total_answered, total_score, session_answered, session_score
           FROM writing_progress
           WHERE user_id = $1 AND type_key = $2 AND level_key = $3""",
        user_id, type_key, level_key
    )
    await conn.close()
    if row:
        return dict(row)
    return None

async def init_writing_session(user_id: int, type_key: str, level_key: str):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO writing_progress (user_id, type_key, level_key, current_index, total_answered, total_score, session_answered, session_score)
        VALUES ($1, $2, $3, 0, 0, 0, 0, 0)
        ON CONFLICT (user_id, type_key, level_key)
        DO UPDATE SET session_answered = 0, session_score = 0
    """, user_id, type_key, level_key)
    await conn.close()

async def get_writing_index(user_id: int, type_key: str, level_key: str) -> int:
    row = await get_writing_progress(user_id, type_key, level_key)
    if row:
        return row['current_index']
    await init_writing_session(user_id, type_key, level_key)
    return 0

async def set_writing_index(user_id: int, type_key: str, level_key: str, index: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO writing_progress (user_id, type_key, level_key, current_index, total_answered, total_score, session_answered, session_score)
        VALUES ($1, $2, $3, $4, 0, 0, 0, 0)
        ON CONFLICT (user_id, type_key, level_key)
        DO UPDATE SET current_index = $4
    """, user_id, type_key, level_key, index)
    await conn.close()

async def get_writing_stats(user_id: int, type_key: str, level_key: str):
    row = await get_writing_progress(user_id, type_key, level_key)
    if row:
        return row['total_answered'], row['total_score'], row['session_answered'], row['session_score']
    return 0, 0, 0, 0

async def update_writing_stats(user_id: int, type_key: str, level_key: str, score: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO writing_progress (user_id, type_key, level_key, current_index, total_answered, total_score, session_answered, session_score)
        VALUES ($1, $2, $3, 0, 1, $4, 1, $4)
        ON CONFLICT (user_id, type_key, level_key)
        DO UPDATE SET
            total_answered = writing_progress.total_answered + 1,
            total_score = writing_progress.total_score + $4,
            session_answered = writing_progress.session_answered + 1,
            session_score = writing_progress.session_score + $4
    """, user_id, type_key, level_key, score)
    await conn.close()

async def reset_writing_progress(user_id: int, type_key: str, level_key: str):
    conn = await get_connection()
    await conn.execute("""
        UPDATE writing_progress
        SET current_index = 0,
            total_answered = 0,
            total_score = 0,
            session_answered = 0,
            session_score = 0
        WHERE user_id = $1 AND type_key = $2 AND level_key = $3
    """, user_id, type_key, level_key)
    await conn.close()

# ---------- Функции для грамматики ----------
async def get_grammar_index(user_id: int, type_key: str, level_key: str) -> int:
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT current_index FROM grammar_progress WHERE user_id = $1 AND type_key = $2 AND level_key = $3",
        user_id, type_key, level_key
    )
    await conn.close()
    if row:
        return row["current_index"]
    await set_grammar_index(user_id, type_key, level_key, 0)
    return 0

async def set_grammar_index(user_id: int, type_key: str, level_key: str, index: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO grammar_progress (user_id, type_key, level_key, current_index)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, type_key, level_key)
        DO UPDATE SET current_index = $4
    """, user_id, type_key, level_key, index)
    await conn.close()

async def reset_grammar_index(user_id: int, type_key: str, level_key: str):
    await set_grammar_index(user_id, type_key, level_key, 0)

async def get_grammar_stats(user_id: int, type_key: str, level_key: str) -> Tuple[int, int]:
    return await get_user_stats_db(user_id, type_key, level_key)

async def update_grammar_stats(user_id: int, type_key: str, level_key: str, correct: bool):
    await update_user_stats_db(user_id, type_key, level_key, correct)

async def reset_grammar_stats(user_id: int, type_key: str, level_key: str):
    await reset_user_stats_db(user_id, type_key, level_key)

async def add_grammar_error(user_id: int, type_key: str, level_key: str, task_index: int):
    await add_reading_error_db(user_id, type_key, level_key, task_index)

async def remove_grammar_error(user_id: int, type_key: str, level_key: str, task_index: int):
    await remove_reading_error_db(user_id, type_key, level_key, task_index)

async def get_grammar_errors(user_id: int, type_key: str, level_key: str) -> List[int]:
    return await get_reading_errors_db(user_id, type_key, level_key)

async def clear_grammar_errors(user_id: int, type_key: str, level_key: str):
    await clear_reading_errors_db(user_id, type_key, level_key)

async def reset_grammar_progress(user_id: int, type_key: str, level_key: str):
    await reset_grammar_index(user_id, type_key, level_key)
    await reset_grammar_stats(user_id, type_key, level_key)
    await clear_grammar_errors(user_id, type_key, level_key)

# ---------- Функции для говорения ----------
async def get_govorenie_progress(user_id: int, task_type: str, level: str):
    conn = await get_connection()
    row = await conn.fetchrow(
        """SELECT current_task_id, total_answered, total_score, session_answered, session_score
           FROM govorenie_progress
           WHERE user_id = $1 AND task_type = $2 AND level = $3""",
        user_id, task_type, level
    )
    await conn.close()
    if row:
        return dict(row)
    return None

async def init_govorenie_session(user_id: int, task_type: str, level: str):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO govorenie_progress (user_id, task_type, level, current_task_id, total_answered, total_score, session_answered, session_score)
        VALUES ($1, $2, $3, 0, 0, 0, 0, 0)
        ON CONFLICT (user_id, task_type, level)
        DO UPDATE SET session_answered = 0, session_score = 0
    """, user_id, task_type, level)
    await conn.close()

async def get_govorenie_task_id(user_id: int, task_type: str, level: str) -> int:
    row = await get_govorenie_progress(user_id, task_type, level)
    if row:
        return row['current_task_id']
    await init_govorenie_session(user_id, task_type, level)
    return 0

async def set_govorenie_task_id(user_id: int, task_type: str, level: str, task_id: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO govorenie_progress (user_id, task_type, level, current_task_id, total_answered, total_score, session_answered, session_score)
        VALUES ($1, $2, $3, $4, 0, 0, 0, 0)
        ON CONFLICT (user_id, task_type, level)
        DO UPDATE SET current_task_id = $4
    """, user_id, task_type, level, task_id)
    await conn.close()

async def get_govorenie_stats(user_id: int, task_type: str, level: str):
    row = await get_govorenie_progress(user_id, task_type, level)
    if row:
        return row['total_answered'], row['total_score'], row['session_answered'], row['session_score']
    return 0, 0, 0, 0

async def update_govorenie_stats(user_id: int, task_type: str, level: str, score: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO govorenie_progress (user_id, task_type, level, current_task_id, total_answered, total_score, session_answered, session_score)
        VALUES ($1, $2, $3, 0, 1, $4, 1, $4)
        ON CONFLICT (user_id, task_type, level)
        DO UPDATE SET
            total_answered = govorenie_progress.total_answered + 1,
            total_score = govorenie_progress.total_score + $4,
            session_answered = govorenie_progress.session_answered + 1,
            session_score = govorenie_progress.session_score + $4
    """, user_id, task_type, level, score)
    await conn.close()

async def reset_govorenie_progress(user_id: int, task_type: str, level: str):
    conn = await get_connection()
    await conn.execute("""
        UPDATE govorenie_progress
        SET current_task_id = 0,
            total_answered = 0,
            total_score = 0,
            session_answered = 0,
            session_score = 0
        WHERE user_id = $1 AND task_type = $2 AND level = $3
    """, user_id, task_type, level)
    await conn.close()

# ---------- Функции для индекса прогресса (универсальные) ----------
async def ensure_progress_index_table():
    # Таблица создаётся в init_db, но на всякий случай проверяем
    pass

async def get_progress_index(user_id: int, type_key: str, level_key: str) -> int:
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT current_index FROM progress_index WHERE user_id = $1 AND type_key = $2 AND level_key = $3",
        user_id, type_key, level_key
    )
    await conn.close()
    if row:
        return row["current_index"]
    await set_progress_index(user_id, type_key, level_key, 0)
    return 0

async def set_progress_index(user_id: int, type_key: str, level_key: str, index: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO progress_index (user_id, type_key, level_key, current_index)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, type_key, level_key)
        DO UPDATE SET current_index = $4
    """, user_id, type_key, level_key, index)
    await conn.close()

async def reset_progress_index(user_id: int, type_key: str, level_key: str):
    await set_progress_index(user_id, type_key, level_key, 0)

# ---------- Функции для случайного порядка ----------
async def ensure_random_order_table():
    # Таблица создаётся в init_db, на всякий случай оставляем пустую функцию
    pass

async def get_random_order(user_id: int, level_key: str) -> list:
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT order_data FROM random_order WHERE user_id = $1 AND level_key = $2",
        user_id, level_key
    )
    await conn.close()
    if row:
        return row["order_data"]
    return None

async def set_random_order(user_id: int, level_key: str, order: list):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO random_order (user_id, level_key, order_data)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (user_id, level_key)
        DO UPDATE SET order_data = $3::jsonb
    """, user_id, level_key, order)
    await conn.close()

# ==============================================
# ---------- НОВЫЕ ФУНКЦИИ ДЛЯ БОНУСНЫХ УВЕДОМЛЕНИЙ ----------
# ==============================================

async def ensure_bonus_columns():
    """Проверяет наличие колонок для бонусов и добавляет их, если отсутствуют."""
    conn = await get_connection()
    await conn.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS bonus_notification BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS bonus_reason TEXT DEFAULT ''
    """)
    await conn.close()

async def set_bonus_notification(user_id: int, reason: str = ""):
    """Устанавливает флаг уведомления о бонусе для пользователя."""
    conn = await get_connection()
    await conn.execute("""
        UPDATE users
        SET bonus_notification = TRUE, bonus_reason = $1
        WHERE user_id = $2
    """, reason, user_id)
    await conn.close()

async def clear_bonus_notification(user_id: int):
    """Сбрасывает флаг уведомления после показа."""
    conn = await get_connection()
    await conn.execute("""
        UPDATE users
        SET bonus_notification = FALSE, bonus_reason = ''
        WHERE user_id = $1
    """, user_id)
    await conn.close()

async def get_bonus_notification(user_id: int):
    """Возвращает (bonus_notification, bonus_reason) для пользователя."""
    conn = await get_connection()
    row = await conn.fetchrow("SELECT bonus_notification, bonus_reason FROM users WHERE user_id = $1", user_id)
    await conn.close()
    if row:
        return row["bonus_notification"], row["bonus_reason"] or ""
    return False, ""

# ---------- ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ АДМИНКИ ----------
async def get_bot_active() -> bool:
    """Возвращает статус активности бота (из bot_settings)."""
    conn = await get_connection()
    val = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'is_active'")
    await conn.close()
    return val == 'true'

async def set_bot_active(active: bool):
    """Устанавливает статус активности бота."""
    conn = await get_connection()
    await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'is_active'", 'true' if active else 'false')
    await conn.close()

async def is_user_blocked(user_id: int) -> bool:
    """Проверяет, заблокирован ли пользователь."""
    conn = await get_connection()
    row = await conn.fetchrow("SELECT 1 FROM blocked_users WHERE user_id = $1", user_id)
    await conn.close()
    return row is not None

async def block_user(user_id: int):
    """Блокирует пользователя."""
    conn = await get_connection()
    await conn.execute("INSERT INTO blocked_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
    await conn.close()

async def unblock_user(user_id: int):
    """Разблокирует пользователя."""
    conn = await get_connection()
    await conn.execute("DELETE FROM blocked_users WHERE user_id = $1", user_id)
    await conn.close()