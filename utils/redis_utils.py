import os
import json
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

async def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)

# ---------- Приветственные сообщения (глобальный индекс) ----------
async def get_global_welcome_index() -> int:
    r = await get_redis()
    val = await r.get("reading_welcome_global_index")
    return int(val) if val else 0

async def increment_global_welcome_index():
    r = await get_redis()
    await r.incr("reading_welcome_global_index")

# ---------- Прогресс пользователя ----------
async def get_user_progress(user_id: int, type_key: str, level_key: str) -> int:
    r = await get_redis()
    key = f"reading_progress:{user_id}:{type_key}:{level_key}"
    val = await r.get(key)
    return int(val) if val else 0

async def set_user_progress(user_id: int, type_key: str, level_key: str, index: int):
    r = await get_redis()
    key = f"reading_progress:{user_id}:{type_key}:{level_key}"
    await r.set(key, str(index))

async def reset_user_progress(user_id: int, type_key: str, level_key: str):
    r = await get_redis()
    key = f"reading_progress:{user_id}:{type_key}:{level_key}"
    await r.delete(key)

# ---------- Статистика пользователя (правильные/неправильные ответы) ----------
async def get_user_stats(user_id: int, type_key: str, level_key: str) -> tuple:
    r = await get_redis()
    key_correct = f"reading_stats:{user_id}:{type_key}:{level_key}:correct"
    key_wrong = f"reading_stats:{user_id}:{type_key}:{level_key}:wrong"
    correct = await r.get(key_correct)
    wrong = await r.get(key_wrong)
    return int(correct) if correct else 0, int(wrong) if wrong else 0

async def update_user_stats(user_id: int, type_key: str, level_key: str, correct: bool):
    r = await get_redis()
    key = f"reading_stats:{user_id}:{type_key}:{level_key}:{'correct' if correct else 'wrong'}"
    await r.incr(key)