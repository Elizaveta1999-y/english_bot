import os
import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import asyncpg
import httpx
from dotenv import load_dotenv
import apscheduler.schedulers.background
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

# ---------- СЛОВАРИ ДЛЯ ОТОБРАЖЕНИЯ КРАСИВЫХ НАЗВАНИЙ ----------
GRAMMAR_TYPES = {
    "раскрытие_скобок": "раскрытие скобок",
    "вставка_пропусков": "вставка пропусков",
    "to_be_выбор": "to be выбор",
    "to_be_скобки": "to be скобки",
    "добавьте_s": "добавьте s",
    "множественное_число": "множественное число",
    "единственное_число": "единственное число",
    "отрицание": "отрицание"
}

LEXIS_TYPES = {
    "adjectives": "Прилагательные",
    "adverbs": "Наречия",
    "verbs": "Глаголы",
    "nouns": "Существительные",
    "conjunctions": "Союзы",
    "prepositions": "Предлоги",
    "phrasal_verbs": "Фразовые глаголы",
    "irregular_verbs": "Неправильные глаголы",
    "false_friends": "Ложные друзья",
    "gold_3000": "Gold 3000",
    "expert": "Эксперт",
    "beginner": "Новичок"
}

LISTENING_TYPES = {
    "choice": "Выбор варианта",
    "truefalse": "True/False/Not stated",
    "fill_one": "Вставка пропуска",
    "fill_multiple": "Вставка пропусков",
    "speaker": "Выбор утверждения",
    "random": "Случайный тип"
}

READING_TYPES = {
    "Подбор_заголовка": "Подбор заголовка",
    "True_False_Not_stated": "True/False/Not stated",
    "Вопросы_с_выбором_ответа": "Вопросы с выбором ответа",
    "Восстановление_порядка_абзацев": "Восстановление порядка абзацев"
}

LEVEL_DISPLAY = {
    "beginner": "Новичок",
    "intermediate": "Любитель",
    "expert": "Эксперт",
    "Новичок": "Новичок",
    "Любитель": "Любитель",
    "Эксперт": "Эксперт"
}

# ---------- БАЗА ДАННЫХ ----------
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
            ADD COLUMN IF NOT EXISTS bonus_reason TEXT DEFAULT '',
            ADD COLUMN IF NOT EXISTS subscription_started BIGINT DEFAULT 0,
            ADD COLUMN IF NOT EXISTS subscription_count INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS speaking_seconds_month BIGINT DEFAULT 0,
            ADD COLUMN IF NOT EXISTS roleplay_seconds_month BIGINT DEFAULT 0
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_balances (
                service TEXT PRIMARY KEY,
                balance TEXT,
                last_updated BIGINT DEFAULT 0,
                threshold TEXT,
                link TEXT
            )
        """)
        await conn.execute("""
            INSERT INTO api_balances (service, balance, threshold, link)
            VALUES ('deepseek', 'неизвестно', '30', 'https://platform.deepseek.com/api_keys'),
                   ('elevenlabs', 'неизвестно', '10000', 'https://elevenlabs.io/app/settings/billing')
            ON CONFLICT (service) DO NOTHING
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS render_payment (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                next_payment_date BIGINT DEFAULT 0,
                amount TEXT DEFAULT '7',
                notified BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("""
            INSERT INTO render_payment (id, next_payment_date, amount, notified)
            VALUES (1, 0, '7', FALSE)
            ON CONFLICT (id) DO NOTHING
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS income (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DECIMAL(10,2) NOT NULL,
                date BIGINT NOT NULL,
                description TEXT
            )
        """)
        await conn.execute("""
            ALTER TABLE income
            ADD COLUMN IF NOT EXISTS payment_system TEXT,
            ADD COLUMN IF NOT EXISTS payment_id TEXT
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                amount DECIMAL(10,2) NOT NULL,
                date BIGINT NOT NULL,
                category TEXT NOT NULL,
                description TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                action TEXT,
                date BIGINT NOT NULL
            )
        """)
        logger.info("✅ Структура БД обновлена")
    except Exception as e:
        logger.error(f"⚠️ Ошибка при обновлении БД: {e}")
    finally:
        await conn.close()

# ---------- ФИНАНСЫ ----------
async def add_income(user_id: int, amount: float, description: str = "", payment_system: str = "", payment_id: str = ""):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    await conn.execute("""
        INSERT INTO income (user_id, amount, date, description, payment_system, payment_id)
        VALUES ($1, $2, $3, $4, $5, $6)
    """, user_id, amount, now, description, payment_system, payment_id)
    await conn.close()

async def add_expense(amount: float, category: str, description: str = ""):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    await conn.execute("""
        INSERT INTO expenses (amount, date, category, description)
        VALUES ($1, $2, $3, $4)
    """, amount, now, category, description)
    await conn.close()

async def get_finance_summary(start_ts: int, end_ts: int) -> dict:
    conn = await get_db()
    income = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM income WHERE date >= $1 AND date <= $2", start_ts, end_ts)
    expenses = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date >= $1 AND date <= $2", start_ts, end_ts)
    await conn.close()
    return {"income": float(income), "expenses": float(expenses)}

async def get_income_list(start_ts: int, end_ts: int, limit: int = 50):
    conn = await get_db()
    rows = await conn.fetch(
        "SELECT id, user_id, amount, date, description, payment_system FROM income WHERE date >= $1 AND date <= $2 ORDER BY date DESC LIMIT $3",
        start_ts, end_ts, limit
    )
    await conn.close()
    return [dict(r) for r in rows]

async def get_expenses_list(start_ts: int, end_ts: int, limit: int = 50):
    conn = await get_db()
    rows = await conn.fetch(
        "SELECT id, amount, date, category, description FROM expenses WHERE date >= $1 AND date <= $2 ORDER BY date DESC LIMIT $3",
        start_ts, end_ts, limit
    )
    await conn.close()
    return [dict(r) for r in rows]

# ---------- ГРАФИКИ ----------
async def get_new_users_data(days: int = 30):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    rows = await conn.fetch(
        "SELECT date_trunc('day', to_timestamp(registered_at)) as day, COUNT(*) as count FROM users WHERE registered_at >= $1 GROUP BY day ORDER BY day",
        start_ts
    )
    await conn.close()
    result = []
    current = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(now)
    data_map = {row["day"].date(): row["count"] for row in rows}
    while current <= end:
        day_date = current.date()
        result.append({
            "date": day_date.isoformat(),
            "count": data_map.get(day_date, 0)
        })
        current += timedelta(days=1)
    return result

async def get_activity_data(days: int = 30):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    rows = await conn.fetch(
        "SELECT date_trunc('day', to_timestamp(date)) as day, COUNT(*) as count FROM activity_log WHERE date >= $1 GROUP BY day ORDER BY day",
        start_ts
    )
    await conn.close()
    if not rows:
        conn = await get_db()
        rows = await conn.fetch(
            "SELECT date_trunc('day', to_timestamp(last_active)) as day, COUNT(*) as count FROM users WHERE last_active >= $1 GROUP BY day ORDER BY day",
            start_ts
        )
        await conn.close()
    result = []
    current = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(now)
    data_map = {row["day"].date(): row["count"] for row in rows}
    while current <= end:
        day_date = current.date()
        result.append({
            "date": day_date.isoformat(),
            "count": data_map.get(day_date, 0)
        })
        current += timedelta(days=1)
    return result

# ---------- WEBHOOK ----------
class PaymentWebhook(BaseModel):
    user_id: int
    amount: float
    description: str = ""
    payment_system: str = ""
    payment_id: str = ""

@app.post("/webhook/payment")
async def payment_webhook(data: PaymentWebhook):
    try:
        await add_income(
            user_id=data.user_id,
            amount=data.amount,
            description=data.description,
            payment_system=data.payment_system,
            payment_id=data.payment_id
        )
        logger.info(f"✅ Доход записан: {data.amount} от пользователя {data.user_id}")
        return {"status": "ok", "message": "Income recorded"}
    except Exception as e:
        logger.error(f"Ошибка записи дохода: {e}")
        return {"status": "error", "message": str(e)}, 500

# ---------- API ДЛЯ ГРАФИКОВ ----------
@app.get("/api/charts-data")
async def charts_data(days: int = 30):
    new_users = await get_new_users_data(days)
    activity = await get_activity_data(days)
    return JSONResponse({"new_users": new_users, "activity": activity})

# ---------- СТРАНИЦЫ ----------
@app.get("/charts", response_class=HTMLResponse)
async def charts_page(request: Request):
    return templates.TemplateResponse("charts.html", {"request": request})

@app.get("/finance", response_class=HTMLResponse)
async def finance_page(request: Request, period: str = "month"):
    now = datetime.now()
    if period == "week":
        start = int((now - timedelta(days=7)).timestamp())
        end = int(now.timestamp())
        label = "за неделю"
    elif period == "month":
        start = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        end = int(now.timestamp())
        label = "за месяц"
    else:
        start = 0
        end = int(now.timestamp())
        label = "за всё время"

    summary = await get_finance_summary(start, end)
    income_list = await get_income_list(start, end)
    expenses_list = await get_expenses_list(start, end)

    for item in income_list:
        item["date_str"] = datetime.fromtimestamp(item["date"]).strftime("%Y-%m-%d %H:%M")
    for item in expenses_list:
        item["date_str"] = datetime.fromtimestamp(item["date"]).strftime("%Y-%m-%d %H:%M")

    return templates.TemplateResponse("finance.html", {
        "request": request,
        "summary": summary,
        "income": income_list,
        "expenses": expenses_list,
        "period": period,
        "label": label
    })

@app.post("/finance/expense")
async def add_expense_route(amount: float = Form(...), category: str = Form(...), description: str = Form("")):
    await add_expense(amount, category, description)
    return RedirectResponse(url="/finance", status_code=303)

# ---------- УПРАВЛЕНИЕ БОТОМ ----------
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

# ---- АВТОРИЗАЦИЯ ----
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

# ---- ГЛАВНАЯ ----
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    conn = await get_db()
    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    now = int(datetime.now().timestamp())
    subscriptions = await conn.fetchval("SELECT COUNT(*) FROM users WHERE subscription_until > $1", now)
    trial_active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trial_until > $1", now)
    total_voice = await conn.fetchval("SELECT COALESCE(SUM(total_voice_seconds_month), 0) FROM users")
    total_voice_minutes = round(total_voice / 60, 1)
    voice_week = total_voice_minutes
    voice_month = total_voice_minutes
    await conn.close()
    stats = {
        "total_users": total_users,
        "subscriptions": subscriptions,
        "trial_active": trial_active,
        "voice_week": voice_week,
        "voice_month": voice_month,
    }
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})

# ---- ПОЛЬЗОВАТЕЛИ ----
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
    users = []
    for row in rows:
        last_active_str = datetime.fromtimestamp(row["last_active"]).strftime("%Y-%m-%d %H:%M") if row["last_active"] else "—"
        users.append({
            "user_id": row["user_id"],
            "username": row["username"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "registered_at": datetime.fromtimestamp(row["registered_at"]).strftime("%Y-%m-%d %H:%M"),
            "last_active": last_active_str,
            "subscription_until": datetime.fromtimestamp(row["subscription_until"]).strftime("%Y-%m-%d") if row["subscription_until"] else "—",
            "trial_until": datetime.fromtimestamp(row["trial_until"]).strftime("%Y-%m-%d") if row["trial_until"] else "—",
            "voice_minutes": round(row["total_voice_seconds_month"] / 60, 1) if row["total_voice_seconds_month"] else 0,
            "is_subscribed": row["subscription_until"] > int(datetime.now().timestamp()) if row["subscription_until"] else False,
            "is_trial": row["trial_until"] > int(datetime.now().timestamp()) if row["trial_until"] else False,
        })
    return templates.TemplateResponse("users.html", {"request": request, "users": users, "search": search})

# ---- ДЕТАЛИ ПОЛЬЗОВАТЕЛЯ (ОБНОВЛЕНА) ----
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
    await conn.close()
    
    user = dict(user_row)
    for field in ["registered_at", "last_active", "subscription_until", "subscription_started", "trial_until", "trial_started"]:
        if user.get(field):
            user[field] = datetime.fromtimestamp(user[field]).strftime("%Y-%m-%d %H:%M") if user[field] else "—"
        else:
            user[field] = "—"
    
    # Подготавливаем данные прогресса
    progress_data = {}
    for r in progress_rows:
        key = r["type_key"]
        level = r["level_key"]
        correct = r["correct"]
        wrong = r["wrong"]
        if key not in progress_data:
            progress_data[key] = {}
        if level not in progress_data[key]:
            progress_data[key][level] = {"correct": 0, "wrong": 0}
        progress_data[key][level]["correct"] += correct
        progress_data[key][level]["wrong"] += wrong
    
    # ---- ГРАММАТИКА (8 подтипов × 3 уровня) ----
    grammar_items = []
    for raw_key, display_name in GRAMMAR_TYPES.items():
        db_key = f"grammar_{raw_key}"
        levels_data = progress_data.get(db_key, {})
        for level in ["Новичок", "Любитель", "Эксперт"]:
            data = levels_data.get(level, {"correct": 0, "wrong": 0})
            correct = data["correct"]
            wrong = data["wrong"]
            total = correct + wrong
            percent = round((correct / total * 100), 1) if total else 0
            grammar_items.append({
                "subtype": display_name,
                "level": level,
                "correct": correct,
                "wrong": wrong,
                "total": total,
                "percent": percent
            })
    
    # ---- ЛЕКСИКА (без уровней, суммируем все уровни) ----
    lexis_items = []
    for raw_key, display_name in LEXIS_TYPES.items():
        db_key = f"words_{raw_key}"
        levels_data = progress_data.get(db_key, {})
        total_correct = 0
        total_wrong = 0
        for level_data in levels_data.values():
            total_correct += level_data["correct"]
            total_wrong += level_data["wrong"]
        total = total_correct + total_wrong
        percent = round((total_correct / total * 100), 1) if total else 0
        lexis_items.append({
            "subtype": display_name,
            "correct": total_correct,
            "wrong": total_wrong,
            "total": total,
            "percent": percent
        })
    
    # ---- ЧТЕНИЕ (4 подтипа × 3 уровня) ----
    reading_items = []
    for raw_key, display_name in READING_TYPES.items():
        db_key = raw_key
        levels_data = progress_data.get(db_key, {})
        for level in ["Новичок", "Любитель", "Эксперт"]:
            data = levels_data.get(level, {"correct": 0, "wrong": 0})
            correct = data["correct"]
            wrong = data["wrong"]
            total = correct + wrong
            percent = round((correct / total * 100), 1) if total else 0
            reading_items.append({
                "subtype": display_name,
                "level": level,
                "correct": correct,
                "wrong": wrong,
                "total": total,
                "percent": percent
            })
    
    # ---- АУДИРОВАНИЕ (6 подтипов × 3 уровня) ----
    listening_items = []
    for raw_key, display_name in LISTENING_TYPES.items():
        db_key = f"listening_{raw_key}"
        levels_data = progress_data.get(db_key, {})
        for level in ["beginner", "intermediate", "expert"]:
            level_display = LEVEL_DISPLAY.get(level, level)
            data = levels_data.get(level, {"correct": 0, "wrong": 0})
            correct = data["correct"]
            wrong = data["wrong"]
            total = correct + wrong
            percent = round((correct / total * 100), 1) if total else 0
            listening_items.append({
                "subtype": display_name,
                "level": level_display,
                "correct": correct,
                "wrong": wrong,
                "total": total,
                "percent": percent
            })
    
    # ---- ПИСЬМО (с уровнями) ----
    writing_items = []
    for r in writing_rows:
        level_display = LEVEL_DISPLAY.get(r["level_key"], r["level_key"])
        answered = r["total_answered"]
        score = r["total_score"]
        avg = round(score / answered, 1) if answered else 0
        writing_items.append({
            "subtype": r["type_key"],
            "level": level_display,
            "answered": answered,
            "score": score,
            "avg": avg
        })
    writing_items.sort(key=lambda x: (x["subtype"], x["level"]))
    
    # ---- ГОВОРЕНИЕ (с уровнями, включая "Эксперт") ----
    govorenie_items = []
    for r in govorenie_rows:
        level_display = LEVEL_DISPLAY.get(r["level"], r["level"])
        answered = r["total_answered"]
        score = r["total_score"]
        avg = round(score / answered, 1) if answered else 0
        govorenie_items.append({
            "subtype": r["task_type"],
            "level": level_display,
            "answered": answered,
            "score": score,
            "avg": avg
        })
    govorenie_items.sort(key=lambda x: (x["subtype"], x["level"]))
    
    # ---- ОБЩЕНИЕ С AI И РОЛЕВЫЕ ИГРЫ ----
    speaking_minutes = round(user.get("speaking_seconds_month", 0) / 60, 1)
    roleplay_minutes = round(user.get("roleplay_seconds_month", 0) / 60, 1)
    
    return templates.TemplateResponse("user_detail.html", {
        "request": request,
        "user": user,
        "grammar_items": grammar_items,
        "lexis_items": lexis_items,
        "reading_items": reading_items,
        "listening_items": listening_items,
        "writing_items": writing_items,
        "govorenie_items": govorenie_items,
        "blocked": blocked,
        "speaking_minutes": speaking_minutes,
        "roleplay_minutes": roleplay_minutes
    })

# ---- УПРАВЛЕНИЕ ПОДПИСКАМИ ----
@app.post("/user/{user_id}/extend")
async def extend_subscription(user_id: int, days: int = Form(...), reason: str = Form("")):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    row = await conn.fetchrow("SELECT subscription_until, subscription_count FROM users WHERE user_id = $1", user_id)
    current = row["subscription_until"] if row and row["subscription_until"] else now
    new_until = max(current, now) + days * 86400
    if current <= now:
        await conn.execute("UPDATE users SET subscription_started = $1 WHERE user_id = $2", now, user_id)
    await conn.execute("UPDATE users SET subscription_until = $1, subscription_count = subscription_count + 1 WHERE user_id = $2", new_until, user_id)
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

@app.post("/user/{user_id}/clear_all_data")
async def clear_all_user_data(user_id: int):
    conn = await get_db()
    await conn.execute("DELETE FROM progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM errors WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM grammar_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM writing_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM govorenie_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM progress_index WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM random_order WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM user_states WHERE user_id = $1", user_id)
    await conn.execute("UPDATE users SET subscription_until = 0, subscription_started = 0, subscription_count = 0, trial_until = 0, trial_started = 0 WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM income WHERE user_id = $1", user_id)
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
async def extend_all_subscriptions(days: int = Form(...)):
    reason = "🎉 Тебе начислены бонусные дни!\nТвоя подписка продлена до 15.08.2026.\nПриносим извинения за временные неудобства и дарим эти дни в качестве компенсации.\nСпасибо за терпение! 🙏"
    conn = await get_db()
    now = int(datetime.now().timestamp())
    await conn.execute("""
        UPDATE users
        SET subscription_until = GREATEST(subscription_until, $1) + $2 * 86400,
            subscription_count = subscription_count + 1,
            subscription_started = CASE WHEN subscription_until <= $1 THEN $1 ELSE subscription_started END
        WHERE subscription_until > 0
    """, now, days)
    await conn.execute("""
        UPDATE users
        SET bonus_notification = TRUE, bonus_reason = $1
        WHERE subscription_until > 0
    """, reason)
    await conn.close()
    return RedirectResponse(url="/", status_code=303)

# ---- УПРАВЛЕНИЕ БОТОМ ----
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
        logger.error(f"Ошибка установки вебхука: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/webhook/disable")
async def disable_webhook():
    try:
        result = await set_webhook(False)
        return {"status": "ok", "message": "Вебхук удалён", "result": result}
    except Exception as e:
        logger.error(f"Ошибка удаления вебхука: {e}")
        return {"status": "error", "message": str(e)}

# ---------- МОНИТОРИНГ ----------
async def get_api_balance(service: str) -> dict:
    conn = await get_db()
    row = await conn.fetchrow("SELECT balance, last_updated, threshold, link FROM api_balances WHERE service = $1", service)
    await conn.close()
    if row:
        threshold = row["threshold"] or "30"
        return {
            "balance": row["balance"] or "неизвестно",
            "last_updated": row["last_updated"] or 0,
            "threshold": threshold,
            "link": row["link"] or "#"
        }
    return {
        "balance": "неизвестно",
        "last_updated": 0,
        "threshold": "30" if service == "deepseek" else "10000",
        "link": "#"
    }

async def update_api_balance(service: str, balance: str, threshold: str = None):
    conn = await get_db()
    now = int(datetime.now().timestamp())
    if threshold is not None:
        await conn.execute("UPDATE api_balances SET balance = $1, last_updated = $2, threshold = $3 WHERE service = $4",
                           balance, now, threshold, service)
    else:
        await conn.execute("UPDATE api_balances SET balance = $1, last_updated = $2 WHERE service = $3",
                           balance, now, service)
    await conn.close()

async def get_render_payment() -> dict:
    conn = await get_db()
    row = await conn.fetchrow("SELECT next_payment_date, amount, notified FROM render_payment WHERE id = 1")
    await conn.close()
    if row:
        return {
            "next_payment_date": row["next_payment_date"] or 0,
            "amount": row["amount"] or "7",
            "notified": row["notified"] or False
        }
    return {"next_payment_date": 0, "amount": "7", "notified": False}

async def set_render_payment(date_ts: int, amount: str):
    conn = await get_db()
    await conn.execute("UPDATE render_payment SET next_payment_date = $1, amount = $2, notified = FALSE WHERE id = 1",
                       date_ts, amount)
    await conn.close()

async def set_render_notified(notified: bool):
    conn = await get_db()
    await conn.execute("UPDATE render_payment SET notified = $1 WHERE id = 1", notified)
    await conn.close()

async def get_deepseek_balance():
    if not DEEPSEEK_API_KEY:
        return "неизвестно"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"DeepSeek API raw response: {data}")
                balance = data.get("total_balance")
                if balance is None:
                    balance = data.get("topped_up_balance")
                if balance is None:
                    balance = data.get("granted_balance")
                if balance is None:
                    balance = data.get("balance")
                if balance is None:
                    return "неизвестно"
                return str(balance)
            else:
                logger.warning(f"DeepSeek API вернул {resp.status_code}: {resp.text}")
                return "ошибка"
    except Exception as e:
        logger.error(f"Ошибка получения баланса DeepSeek: {e}")
        return "ошибка"

async def get_elevenlabs_balance():
    if not ELEVENLABS_API_KEY:
        return "неизвестно"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": ELEVENLABS_API_KEY}
            )
            if resp.status_code == 200:
                data = resp.json()
                limit = data.get("character_limit", 0)
                used = data.get("character_count", 0)
                remaining = max(0, limit - used) if limit else 0
                return str(remaining)
            else:
                logger.warning(f"ElevenLabs API вернул {resp.status_code}")
                return "ошибка"
    except Exception as e:
        logger.error(f"Ошибка получения баланса ElevenLabs: {e}")
        return "ошибка"

async def send_telegram_alert(message: str):
    admin_id = os.getenv("ADMIN_ID")
    bot_token = os.getenv("BOT_TOKEN")
    if not admin_id or not bot_token:
        logger.warning("ADMIN_ID или BOT_TOKEN не заданы, уведомление не отправлено")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": admin_id, "text": message})
        logger.info(f"Уведомление отправлено админу: {message[:50]}...")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление: {e}")

async def check_balances_and_notify():
    logger.info("Запущена проверка балансов")
    try:
        deepseek_data = await get_api_balance("deepseek")
        elevenlabs_data = await get_api_balance("elevenlabs")
        if not deepseek_data or not elevenlabs_data:
            logger.warning("Нет данных о балансах в БД")
            return

        deepseek_balance = await get_deepseek_balance()
        elevenlabs_balance = await get_elevenlabs_balance()

        await update_api_balance("deepseek", deepseek_balance or "неизвестно")
        await update_api_balance("elevenlabs", elevenlabs_balance or "неизвестно")

        try:
            threshold_str = deepseek_data.get("threshold") or "30"
            deep_threshold = float(threshold_str)
            if deepseek_balance and deepseek_balance.replace('.', '').isdigit():
                deep_val = float(deepseek_balance)
            else:
                deep_val = float('inf')
            if deep_val < deep_threshold:
                await send_telegram_alert(
                    f"⚠️ Баланс DeepSeek: {deepseek_balance} CNY (порог {deep_threshold} CNY)\nПополните: https://platform.deepseek.com/api_keys"
                )
        except Exception as e:
            logger.error(f"Ошибка проверки DeepSeek: {e}")

        try:
            threshold_str = elevenlabs_data.get("threshold") or "10000"
            elev_threshold = int(threshold_str)
            if elevenlabs_balance and elevenlabs_balance.isdigit():
                elev_val = int(elevenlabs_balance)
            else:
                elev_val = float('inf')
            if elev_val < elev_threshold:
                await send_telegram_alert(
                    f"⚠️ Остаток символов ElevenLabs: {elevenlabs_balance} (порог {elev_threshold})\nПополните: https://elevenlabs.io/app/settings/billing"
                )
        except Exception as e:
            logger.error(f"Ошибка проверки ElevenLabs: {e}")

        render_data = await get_render_payment()
        if render_data and render_data.get("next_payment_date"):
            now = int(datetime.now().timestamp())
            days_left = (render_data["next_payment_date"] - now) // 86400
            if days_left <= 3 and days_left >= 0 and not render_data.get("notified", False):
                await send_telegram_alert(
                    f"⏰ Через {days_left} дней списание ${render_data.get('amount', '7')} за Render.\nПроверьте баланс: https://dashboard.render.com/billing"
                )
                await set_render_notified(True)
        logger.info("Проверка балансов завершена")
    except Exception as e:
        logger.error(f"Ошибка в check_balances_and_notify: {e}")

# ---- СТРАНИЦА МОНИТОРИНГА ----
@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request):
    try:
        deepseek = await get_api_balance("deepseek")
        elevenlabs = await get_api_balance("elevenlabs")
        render = await get_render_payment()

        if not deepseek or deepseek.get("balance") == "неизвестно":
            await update_api_balance("deepseek", "неизвестно", "30")
            deepseek = await get_api_balance("deepseek")
        if not elevenlabs or elevenlabs.get("balance") == "неизвестно":
            await update_api_balance("elevenlabs", "неизвестно", "10000")
            elevenlabs = await get_api_balance("elevenlabs")
        if not render or render.get("next_payment_date") == 0:
            await set_render_payment(0, "7")
            render = await get_render_payment()

        def safe_float(val):
            try:
                return float(val) if val is not None and str(val).replace('.', '').isdigit() else 0.0
            except:
                return 0.0

        def safe_int(val):
            try:
                return int(val) if val is not None and str(val).isdigit() else 0
            except:
                return 0

        deepseek_balance_str = deepseek.get("balance", "неизвестно")
        deepseek_numeric = {
            "balance": deepseek_balance_str,
            "balance_float": safe_float(deepseek_balance_str),
            "threshold": deepseek.get("threshold", "30"),
            "threshold_float": safe_float(deepseek.get("threshold", "30")),
            "last_updated": deepseek.get("last_updated", 0),
            "link": deepseek.get("link", "#")
        }

        elevenlabs_balance_str = elevenlabs.get("balance", "неизвестно")
        elevenlabs_numeric = {
            "balance": elevenlabs_balance_str,
            "balance_int": safe_int(elevenlabs_balance_str),
            "threshold": elevenlabs.get("threshold", "10000"),
            "threshold_int": safe_int(elevenlabs.get("threshold", "10000")),
            "last_updated": elevenlabs.get("last_updated", 0),
            "link": elevenlabs.get("link", "#")
        }

        deepseek_last = datetime.fromtimestamp(deepseek_numeric["last_updated"]).strftime("%Y-%m-%d %H:%M") if deepseek_numeric["last_updated"] else "—"
        elevenlabs_last = datetime.fromtimestamp(elevenlabs_numeric["last_updated"]).strftime("%Y-%m-%d %H:%M") if elevenlabs_numeric["last_updated"] else "—"

        render_next_date = datetime.fromtimestamp(render["next_payment_date"]).strftime("%Y-%m-%d") if render["next_payment_date"] else "—"
        render_date_input = datetime.fromtimestamp(render["next_payment_date"]).strftime("%Y-%m-%d") if render["next_payment_date"] else ""
        days_left = None
        if render["next_payment_date"]:
            now = int(datetime.now().timestamp())
            days_left = (render["next_payment_date"] - now) // 86400

        return templates.TemplateResponse("monitoring.html", {
            "request": request,
            "deepseek": deepseek_numeric,
            "elevenlabs": elevenlabs_numeric,
            "render": {
                "next_date": render_next_date,
                "next_date_input": render_date_input,
                "amount": render["amount"],
                "days_left": days_left
            }
        })
    except Exception as e:
        logger.error(f"Ошибка на странице мониторинга: {e}")
        return HTMLResponse(f"<h1>Ошибка</h1><pre>{e}</pre>", status_code=500)

@app.post("/monitoring/update/deepseek")
async def update_deepseek_now():
    try:
        bal = await get_deepseek_balance()
        await update_api_balance("deepseek", bal or "неизвестно")
    except Exception as e:
        logger.error(f"Ошибка обновления DeepSeek: {e}")
    return RedirectResponse(url="/monitoring", status_code=303)

@app.post("/monitoring/update/elevenlabs")
async def update_elevenlabs_now():
    try:
        bal = await get_elevenlabs_balance()
        await update_api_balance("elevenlabs", bal or "неизвестно")
    except Exception as e:
        logger.error(f"Ошибка обновления ElevenLabs: {e}")
    return RedirectResponse(url="/monitoring", status_code=303)

@app.post("/monitoring/render")
async def set_render_date(request: Request, date: str = Form(...), amount: str = Form(...)):
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        ts = int(dt.timestamp())
    except:
        ts = 0
    await set_render_payment(ts, amount)
    return RedirectResponse(url="/monitoring", status_code=303)

# ---------- ЗАПУСК ----------
@app.on_event("startup")
async def startup():
    await ensure_db_structure()
    scheduler = apscheduler.schedulers.background.BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run(check_balances_and_notify()), 'interval', hours=6, id='monitor_balances')
    scheduler.start()
    logger.info("✅ Фоновый мониторинг запущен (каждые 6 часов)")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("admin_app:app", host="0.0.0.0", port=8000, reload=True)