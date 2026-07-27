import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def ensure_db_structure():
    conn = await get_db()
    try:
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('is_active', 'true')
            ON CONFLICT (key) DO NOTHING
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id BIGINT PRIMARY KEY
            )
        """)
        print("✅ Структура БД обновлена")
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении БД: {e}")
    finally:
        await conn.close()

@app.on_event("startup")
async def startup():
    await ensure_db_structure()

def is_authenticated(request: Request) -> bool:
    return request.cookies.get("admin_auth") == "true"

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in ["/login", "/favicon.ico"]:
        return await call_next(request)
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return await call_next(request)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="admin_auth", value="true", httponly=True, max_age=86400)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("admin_auth")
    return response

async def get_bot_active() -> bool:
    conn = await get_db()
    val = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'is_active'")
    await conn.close()
    return val == 'true'

async def set_bot_active(active: bool):
    conn = await get_db()
    await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = 'is_active'", 'true' if active else 'false')
    await conn.close()

async def is_user_blocked(user_id: int) -> bool:
    conn = await get_db()
    row = await conn.fetchrow("SELECT 1 FROM blocked_users WHERE user_id = $1", user_id)
    await conn.close()
    return row is not None

async def block_user(user_id: int):
    conn = await get_db()
    await conn.execute("INSERT INTO blocked_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
    await conn.close()

async def unblock_user(user_id: int):
    conn = await get_db()
    await conn.execute("DELETE FROM blocked_users WHERE user_id = $1", user_id)
    await conn.close()

async def set_bonus_notification(user_id: int, reason: str):
    conn = await get_db()
    await conn.execute("UPDATE users SET bonus_notification = TRUE, bonus_reason = $1 WHERE user_id = $2", reason, user_id)
    await conn.close()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    conn = await get_db()
    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    week_ago = int((datetime.now() - timedelta(days=7)).timestamp())
    active_week = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_active > $1", week_ago)
    now = int(datetime.now().timestamp())
    subscriptions = await conn.fetchval("SELECT COUNT(*) FROM users WHERE subscription_until > $1", now)
    trial_active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trial_until > $1", now)
    total_voice = await conn.fetchval("SELECT COALESCE(SUM(total_voice_seconds_month), 0) FROM users")
    blocked_count = await conn.fetchval("SELECT COUNT(*) FROM blocked_users")
    is_active = await get_bot_active()
    await conn.close()
    stats = {
        "total_users": total_users,
        "active_week": active_week,
        "subscriptions": subscriptions,
        "trial_active": trial_active,
        "total_voice_minutes": round(total_voice / 60, 1),
        "blocked_count": blocked_count,
        "is_active": is_active
    }
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})

@app.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, search: str = ""):
    conn = await get_db()
    query = """
        SELECT user_id, username, first_name, last_name,
               registered_at, last_active, subscription_until, trial_until,
               total_voice_seconds_month
        FROM users
        WHERE (user_id::text ILIKE $1 OR username ILIKE $1 OR first_name ILIKE $1 OR last_name ILIKE $1)
        ORDER BY user_id DESC
        LIMIT 100
    """
    search_pattern = f"%{search}%" if search else "%%"
    rows = await conn.fetch(query, search_pattern)
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
    return templates.TemplateResponse("users.html", {"request": request, "users": users, "search": search})

@app.get("/user/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: int):
    conn = await get_db()
    user_row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    if not user_row:
        raise HTTPException(404, "Пользователь не найден")
    blocked = await is_user_blocked(user_id)
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
        "errors": errors_summary,
        "blocked": blocked
    })

@app.post("/user/{user_id}/extend")
async def extend_subscription(user_id: int, days: int = Form(...), reason: str = Form("")):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    row = await conn.fetchrow("SELECT subscription_until FROM users WHERE user_id = $1", user_id)
    current = row["subscription_until"] if row and row["subscription_until"] else now
    new_until = max(current, now) + days * 86400
    await conn.execute("UPDATE users SET subscription_until = $1 WHERE user_id = $2", new_until, user_id)
    if reason.strip():
        await set_bonus_notification(user_id, reason)
    await conn.close()
    return RedirectResponse(url=f"/user/{user_id}", status_code=303)

@app.post("/user/{user_id}/cancel")
async def cancel_subscription(user_id: int):
    conn = await get_db()
    await conn.execute("UPDATE users SET subscription_until = 0 WHERE user_id = $1", user_id)
    await conn.close()
    return RedirectResponse(url=f"/user/{user_id}", status_code=303)

@app.post("/user/{user_id}/reset_progress")
async def reset_user_progress(user_id: int):
    conn = await get_db()
    await conn.execute("DELETE FROM progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM errors WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM grammar_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM writing_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM govorenie_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM progress_index WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM random_order WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM user_states WHERE user_id = $1", user_id)
    await conn.close()
    return RedirectResponse(url=f"/user/{user_id}", status_code=303)

@app.post("/user/{user_id}/block")
async def block_user_route(user_id: int):
    await block_user(user_id)
    return RedirectResponse(url=f"/user/{user_id}", status_code=303)

@app.post("/user/{user_id}/unblock")
async def unblock_user_route(user_id: int):
    await unblock_user(user_id)
    return RedirectResponse(url=f"/user/{user_id}", status_code=303)

@app.post("/extend_all")
async def extend_all_subscriptions(days: int = Form(...), reason: str = Form("")):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    await conn.execute("""
        UPDATE users
        SET subscription_until = GREATEST(subscription_until, $1) + $2 * 86400
        WHERE subscription_until > 0
    """, now, days)
    if reason.strip():
        await conn.execute("""
            UPDATE users
            SET bonus_notification = TRUE, bonus_reason = $1
            WHERE subscription_until > 0
        """, reason)
    await conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/bot/toggle")
async def toggle_bot(active: bool = Form(...)):
    await set_bot_active(active)
    return RedirectResponse(url="/bot", status_code=303)

@app.get("/bot", response_class=HTMLResponse)
async def bot_control(request: Request):
    is_active = await get_bot_active()
    return templates.TemplateResponse("bot_control.html", {"request": request, "is_active": is_active})

async def set_webhook(enable: bool):
    if enable:
        if not WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL не задан")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}"
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.json()

@app.post("/webhook/enable")
async def enable_webhook():
    try:
        result = await set_webhook(True)
        return {"status": "ok", "message": "Вебхук установлен", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/webhook/disable")
async def disable_webhook():
    try:
        result = await set_webhook(False)
        return {"status": "ok", "message": "Вебхук удалён", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("admin_app:app", host="0.0.0.0", port=8000, reload=True)