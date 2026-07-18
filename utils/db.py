import sqlite3
import os
from typing import Tuple, List, Optional

DB_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

def get_connection():
    """Возвращает соединение с БД и включает режим Row."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создаёт таблицы, если их нет. Вызвать один раз при запуске бота."""
    conn = get_connection()
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

# ---------- Пользователи ----------
def get_or_create_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    conn = get_connection()
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

# ---------- Прогресс ----------
def get_user_stats_db(user_id: int, type_key: str, level_key: str) -> Tuple[int, int]:
    conn = get_connection()
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

def update_user_stats_db(user_id: int, type_key: str, level_key: str, correct: bool):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO progress (user_id, type_key, level_key, correct, wrong) VALUES (?, ?, ?, 0, 0) "
        "ON CONFLICT(user_id, type_key, level_key) DO UPDATE SET "
        f"{'correct' if correct else 'wrong'} = {'correct' if correct else 'wrong'} + 1",
        (user_id, type_key, level_key)
    )
    conn.commit()
    conn.close()

def reset_user_stats_db(user_id: int, type_key: str, level_key: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM progress WHERE user_id = ? AND type_key = ? AND level_key = ?",
        (user_id, type_key, level_key)
    )
    conn.commit()
    conn.close()

# ---------- Ошибки ----------
def add_reading_error_db(user_id: int, type_key: str, level_key: str, task_index: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO errors (user_id, type_key, level_key, task_index) VALUES (?, ?, ?, ?)",
        (user_id, type_key, level_key, task_index)
    )
    conn.commit()
    conn.close()

def remove_reading_error_db(user_id: int, type_key: str, level_key: str, task_index: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM errors WHERE user_id = ? AND type_key = ? AND level_key = ? AND task_index = ?",
        (user_id, type_key, level_key, task_index)
    )
    conn.commit()
    conn.close()

def get_reading_errors_db(user_id: int, type_key: str, level_key: str) -> List[int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT task_index FROM errors WHERE user_id = ? AND type_key = ? AND level_key = ?",
        (user_id, type_key, level_key)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row["task_index"] for row in rows]

def clear_reading_errors_db(user_id: int, type_key: str, level_key: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM errors WHERE user_id = ? AND type_key = ? AND level_key = ?",
        (user_id, type_key, level_key)
    )
    conn.commit()
    conn.close()

# ---------- Дополнительно: сброс всего прогресса пользователя ----------
def reset_all_user_progress(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM errors WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()