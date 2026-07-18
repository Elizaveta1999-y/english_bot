import sqlite3
import os
import asyncio
from typing import Tuple, List, Optional

DB_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

def _get_connection():
    """Синхронная функция для получения соединения."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db_sync():
    """Синхронная инициализация таблиц."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            subscription_end INTEGER DEFAULT 0,
            registered_at INTEGER DEFAULT (strftime('%s', 'now')),
            last_active INTEGER DEFAULT (strftime('%s', 'now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            user_id INTEGER NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, type_key, level_key)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            user_id INTEGER NOT NULL,
            type_key TEXT NOT NULL,
            level_key TEXT NOT NULL,
            task_index INTEGER NOT NULL,
            PRIMARY KEY (user_id, type_key, level_key, task_index)
        )
    """)
    conn.commit()
    conn.close()

async def init_db():
    """Асинхронная инициализация БД."""
    await asyncio.to_thread(_init_db_sync)

# ---------- Пользователи ----------
def _get_or_create_user_sync(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, last_name)
    )
    cursor.execute(
        "UPDATE users SET last_active = strftime('%s', 'now') WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    return await asyncio.to_thread(_get_or_create_user_sync, user_id, username, first_name, last_name)

# ---------- Прогресс ----------
def _get_user_stats_sync(user_id: int, type_key: str, level_key: str) -> Tuple[int, int]:
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT correct, wrong FROM progress WHERE user_id = ? AND type_key = ? AND level_key = ?",
        (user_id, type_key, level_key)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return row["correct"], row["wrong"]
    return 0, 0

async def get_user_stats_db(user_id: int, type_key: str, level_key: str) -> Tuple[int, int]:
    return await asyncio.to_thread(_get_user_stats_sync, user_id, type_key, level_key)

def _update_user_stats_sync(user_id: int, type_key: str, level_key: str, correct: bool):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO progress (user_id, type_key, level_key, correct, wrong) VALUES (?, ?, ?, 0, 0) "
        "ON CONFLICT(user_id, type_key, level_key) DO UPDATE SET "
        f"{'correct' if correct else 'wrong'} = {'correct' if correct else 'wrong'} + 1",
        (user_id, type_key, level_key)
    )
    conn.commit()
    conn.close()

async def update_user_stats_db(user_id: int, type_key: str, level_key: str, correct: bool):
    await asyncio.to_thread(_update_user_stats_sync, user_id, type_key, level_key, correct)

def _reset_user_stats_sync(user_id: int, type_key: str, level_key: str):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM progress WHERE user_id = ? AND type_key = ? AND level_key = ?",
        (user_id, type_key, level_key)
    )
    conn.commit()
    conn.close()

async def reset_user_stats_db(user_id: int, type_key: str, level_key: str):
    await asyncio.to_thread(_reset_user_stats_sync, user_id, type_key, level_key)

# ---------- Ошибки ----------
def _add_reading_error_sync(user_id: int, type_key: str, level_key: str, task_index: int):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO errors (user_id, type_key, level_key, task_index) VALUES (?, ?, ?, ?)",
        (user_id, type_key, level_key, task_index)
    )
    conn.commit()
    conn.close()

async def add_reading_error_db(user_id: int, type_key: str, level_key: str, task_index: int):
    await asyncio.to_thread(_add_reading_error_sync, user_id, type_key, level_key, task_index)

def _remove_reading_error_sync(user_id: int, type_key: str, level_key: str, task_index: int):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM errors WHERE user_id = ? AND type_key = ? AND level_key = ? AND task_index = ?",
        (user_id, type_key, level_key, task_index)
    )
    conn.commit()
    conn.close()

async def remove_reading_error_db(user_id: int, type_key: str, level_key: str, task_index: int):
    await asyncio.to_thread(_remove_reading_error_sync, user_id, type_key, level_key, task_index)

def _get_reading_errors_sync(user_id: int, type_key: str, level_key: str) -> List[int]:
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT task_index FROM errors WHERE user_id = ? AND type_key = ? AND level_key = ?",
        (user_id, type_key, level_key)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row["task_index"] for row in rows]

async def get_reading_errors_db(user_id: int, type_key: str, level_key: str) -> List[int]:
    return await asyncio.to_thread(_get_reading_errors_sync, user_id, type_key, level_key)

def _clear_reading_errors_sync(user_id: int, type_key: str, level_key: str):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM errors WHERE user_id = ? AND type_key = ? AND level_key = ?",
        (user_id, type_key, level_key)
    )
    conn.commit()
    conn.close()

async def clear_reading_errors_db(user_id: int, type_key: str, level_key: str):
    await asyncio.to_thread(_clear_reading_errors_sync, user_id, type_key, level_key)

# ---------- Сброс всего прогресса пользователя ----------
def _reset_all_user_progress_sync(user_id: int):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM errors WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

async def reset_all_user_progress(user_id: int):
    await asyncio.to_thread(_reset_all_user_progress_sync, user_id)