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
    # Таблица прогресса для других режимов (чтение/грамматика и т.п.)
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
    # Таблица ошибок (для чтения)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            user_id BIGINT NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            task_index INTEGER NOT NULL,
            PRIMARY KEY (user_id, type_key, level_key, task_index)
        )
    """)
    # Таблица для прогресса письма (с расширенной статистикой)
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
            user_id BIGINT PRIMARY KEY,
            current_index INTEGER DEFAULT 0
        )
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

# ---------- Прогресс (для других режимов, например чтение) ----------
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

# ---------- Ошибки (для чтения) ----------
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
    """Создаёт запись, если нет, и обнуляет session_answered, session_score"""
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
    """Возвращает (total_answered, total_score, session_answered, session_score)"""
    row = await get_writing_progress(user_id, type_key, level_key)
    if row:
        return row['total_answered'], row['total_score'], row['session_answered'], row['session_score']
    return 0, 0, 0, 0

async def update_writing_stats(user_id: int, type_key: str, level_key: str, score: int):
    """Увеличивает все счётчики на 1 и добавляет score"""
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
    """Полный сброс: обнуляем всё (индекс, статистику, сессию)"""
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
async def get_grammar_index(user_id: int) -> int:
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT current_index FROM grammar_progress WHERE user_id = $1",
        user_id
    )
    await conn.close()
    if row:
        return row["current_index"]
    await set_grammar_index(user_id, 0)
    return 0

async def set_grammar_index(user_id: int, index: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO grammar_progress (user_id, current_index)
        VALUES ($1, $2)
        ON CONFLICT (user_id)
        DO UPDATE SET current_index = $2
    """, user_id, index)
    await conn.close()