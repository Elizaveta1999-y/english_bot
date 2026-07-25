import os
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import asyncpg

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env or environment")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Для управления ботом нам понадобится bot token и функция установки/удаления вебхука
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

# ---- Вспомогательные функции для работы с вебхуком ----
async def set_webhook():
    """Устанавливает вебхук для бота (включает бота)"""
    import aiohttp
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        # для локального теста можно указать ngrok или localhost с портом
        external_url = "https://your-domain.onrender.com"  # замените на ваш домен
    webhook_url = f"{external_url}/webhook"
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
        async with session.get(url) as resp:
            return await resp.json()

async def delete_webhook():
    """Удаляет вебхук (выключает бота)"""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        async with session.get(url) as resp:
            return await resp.json()

async def get_webhook_info():
    """Получает информацию о вебхуке (статус бота)"""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        async with session.get(url) as resp:
            return await resp.json()

# ---- Главная страница ----
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, password: str = None):
    if password != ADMIN_PASSWORD:
        return HTMLResponse("<h1>Доступ запрещён</h1><p>Используйте ?password=ваш_пароль</p>", status_code=401)
    
    conn = await get_db()
    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    week_ago = int((datetime.now() - timedelta(days=7)).timestamp())
    active_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_active > $1", week_ago)
    now = int(datetime.now().timestamp())
    subscriptions = await conn.fetchval("SELECT COUNT(*) FROM users WHERE subscription_until > $1", now)
    trial_active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trial_until > $1", now)
    total_voice = await conn.fetchval("SELECT COALESCE(SUM(total_voice_seconds_month), 0) FROM users")
    await conn.close()

    # Получаем статус бота
    webhook_info = await get_webhook_info()
    bot_status = "🟢 Включён" if webhook_info.get("url") else "🔴 Выключен"
    if webhook_info.get("url"):
        bot_status += f" (вебхук: {webhook_info['url']})"

    stats = {
        "total_users": total_users,
        "active_week": active_week,
        "subscriptions": subscriptions,
        "trial_active": trial_active,
        "total_voice_minutes": round(total_voice / 60, 1),
        "bot_status": bot_status,
        "bot_is_active": bool(webhook_info.get("url"))
    }
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})

# ---- Управление ботом (вкл/выкл) ----
@app.post("/bot/enable")
async def enable_bot(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "Неверный пароль")
    result = await set_webhook()
    if result.get("ok"):
        return RedirectResponse(url="/?password=" + password, status_code=303)
    else:
        return HTMLResponse(f"<h1>Ошибка</h1><p>{result}</p>", status_code=500)

@app.post("/bot/disable")
async def disable_bot(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "Неверный пароль")
    result = await delete_webhook()
    if result.get("ok"):
        return RedirectResponse(url="/?password=" + password, status_code=303)
    else:
        return HTMLResponse(f"<h1>Ошибка</h1><p>{result}</p>", status_code=500)

# ---- Список пользователей ----
@app.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, password: str = None):
    if password != ADMIN_PASSWORD:
        return HTMLResponse("<h1>Доступ запрещён</h1>", status_code=401)
    conn = await get_db()
    rows = await conn.fetch("""
        SELECT user_id, username, first_name, last_name,
               registered_at, last_active, subscription_until, trial_until,
               total_voice_seconds_month
        FROM users ORDER BY user_id DESC LIMIT 100
    """)
    await conn.close()
    now_ts = int(datetime.now().timestamp())
    users = []
    for row in rows:
        users.append({
            "user_id": row["user_id"],
            "username": row["username"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "registered_at": datetime.fromtimestamp(row["registered_at"]).strftime("%Y-%m-%d %H:%M"),
            "last_active": datetime.fromtimestamp(row["last_active"]).strftime("%Y-%m-%d %H:%M") if row["last_active"] else "—",
            "subscription_until": datetime.fromtimestamp(row["subscription_until"]).strftime("%Y-%m-%d") if row["subscription_until"] else "—",
            "trial_until": datetime.fromtimestamp(row["trial_until"]).strftime("%Y-%m-%d") if row["trial_until"] else "—",
            "voice_minutes": round(row["total_voice_seconds_month"] / 60, 1) if row["total_voice_seconds_month"] else 0,
            "is_subscribed": row["subscription_until"] > now_ts if row["subscription_until"] else False,
            "is_trial": row["trial_until"] > now_ts if row["trial_until"] else False,
        })
    return templates.TemplateResponse("users.html", {"request": request, "users": users})

# ---- Детальная страница пользователя ----
@app.get("/user/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: int, password: str = None):
    if password != ADMIN_PASSWORD:
        return HTMLResponse("<h1>Доступ запрещён</h1>", status_code=401)
    conn = await get_db()
    user_row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    if not user_row:
        raise HTTPException(404, "Пользователь не найден")
    progress_rows = await conn.fetch("SELECT type_key, level_key, correct, wrong FROM progress WHERE user_id = $1", user_id)
    writing_rows = await conn.fetch("SELECT type_key, level_key, total_answered, total_score FROM writing_progress WHERE user_id = $1", user_id)
    govorenie_rows = await conn.fetch("SELECT task_type, level, total_answered, total_score FROM govorenie_progress WHERE user_id = $1", user_id)
    error_rows = await conn.fetch("SELECT type_key, COUNT(*) as cnt FROM errors WHERE user_id = $1 GROUP BY type_key", user_id)
    await conn.close()
    user = dict(user_row)
    progress_summary = {}
    for r in progress_rows:
        key = r["type_key"]
        if key not in progress_summary:
            progress_summary[key] = {"correct": 0, "wrong": 0}
        progress_summary[key]["correct"] += r["correct"]
        progress_summary[key]["wrong"] += r["wrong"]
    writing_summary = {}
    for r in writing_rows:
        key = r["type_key"]
        writing_summary[key] = {"answered": r["total_answered"], "score": r["total_score"]}
    govorenie_summary = {}
    for r in govorenie_rows:
        key = r["task_type"]
        govorenie_summary[key] = {"answered": r["total_answered"], "score": r["total_score"]}
    errors_summary = {r["type_key"]: r["cnt"] for r in error_rows}
    return templates.TemplateResponse("user_detail.html", {
        "request": request,
        "user": user,
        "progress": progress_summary,
        "writing": writing_summary,
        "govorenie": govorenie_summary,
        "errors": errors_summary
    })

# ---- Продлить подписку ----
@app.post("/user/{user_id}/extend")
async def extend_subscription(user_id: int, days: int = Form(...), password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "Неверный пароль")
    conn = await get_db()
    now = int(datetime.now().timestamp())
    row = await conn.fetchrow("SELECT subscription_until FROM users WHERE user_id = $1", user_id)
    current = row["subscription_until"] if row and row["subscription_until"] else now
    new_until = max(current, now) + days * 86400
    await conn.execute("UPDATE users SET subscription_until = $1 WHERE user_id = $2", new_until, user_id)
    await conn.close()
    return RedirectResponse(url=f"/user/{user_id}?password={password}", status_code=303)

# ---- Отменить подписку ----
@app.post("/user/{user_id}/cancel")
async def cancel_subscription(user_id: int, password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "Неверный пароль")
    conn = await get_db()
    await conn.execute("UPDATE users SET subscription_until = 0 WHERE user_id = $1", user_id)
    await conn.close()
    return RedirectResponse(url=f"/user/{user_id}?password={password}", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("admin_app:app", host="0.0.0.0", port=8000, reload=True)