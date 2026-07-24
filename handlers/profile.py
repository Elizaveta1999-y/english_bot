from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# Правильный импорт из utils/db.py
from utils.db import (
    get_connection,
    get_user_stats_db,
    reset_user_stats_db,
    get_writing_progress,
    get_govorenie_progress,
    reset_writing_progress,
    reset_govorenie_progress,
    clear_reading_errors_db,
    reset_grammar_progress,
    reset_all_user_progress,
    get_or_create_user,
)

from handlers.start import show_main_menu

router = Router()

# ---------- Вспомогательные функции для работы с БД (отсутствуют в db.py) ----------

async def get_user_profile(user_id: int):
    """Возвращает запись пользователя из таблицы users"""
    conn = await get_connection()
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return dict(row) if row else None

async def update_last_active(user_id: int):
    """Обновляет время последней активности"""
    conn = await get_connection()
    await conn.execute(
        "UPDATE users SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT WHERE user_id = $1",
        user_id
    )
    await conn.close()

async def calculate_streak(user_id: int) -> int:
    """Упрощённый подсчёт серии (только проверка активности сегодня)"""
    profile = await get_user_profile(user_id)
    if not profile:
        return 0
    last_ts = profile.get("last_active")
    if not last_ts:
        return 0
    last_date = datetime.fromtimestamp(last_ts).date()
    today = datetime.now().date()
    delta = (today - last_date).days
    if delta == 0:
        return 1
    elif delta == 1:
        return 1   # можно увеличивать, если хранить историю, но пока так
    else:
        return 0

async def get_progress_summary(user_id: int, type_key: str) -> dict:
    """Суммирует correct и wrong по всем уровням для заданного type_key"""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT SUM(correct) as correct, SUM(wrong) as wrong FROM progress WHERE user_id = $1 AND type_key = $2",
        user_id, type_key
    )
    await conn.close()
    correct = row["correct"] if row and row["correct"] else 0
    wrong = row["wrong"] if row and row["wrong"] else 0
    total = correct + wrong
    percent = round((correct / total * 100)) if total else 0
    return {"correct": correct, "wrong": wrong, "total": total, "percent": percent}

async def get_writing_summary(user_id: int) -> dict:
    """Суммирует данные из writing_progress"""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT SUM(total_answered) as answered, SUM(total_score) as score_sum FROM writing_progress WHERE user_id = $1",
        user_id
    )
    await conn.close()
    answered = row["answered"] if row and row["answered"] else 0
    score_sum = row["score_sum"] if row and row["score_sum"] else 0
    avg = round(score_sum / answered, 1) if answered else 0.0
    return {"answered": answered, "score_sum": score_sum, "avg": avg}

async def get_speaking_summary(user_id: int) -> dict:
    """Суммирует данные из govorenie_progress"""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT SUM(total_answered) as answered, SUM(total_score) as score_sum FROM govorenie_progress WHERE user_id = $1",
        user_id
    )
    await conn.close()
    answered = row["answered"] if row and row["answered"] else 0
    score_sum = row["score_sum"] if row and row["score_sum"] else 0
    avg = round(score_sum / answered, 1) if answered else 0.0
    return {"answered": answered, "score_sum": score_sum, "avg": avg}

async def count_user_errors(user_id: int) -> dict:
    """Считает ошибки из таблицы errors"""
    conn = await get_connection()
    rows = await conn.fetch(
        "SELECT type_key, COUNT(*) as cnt FROM errors WHERE user_id = $1 GROUP BY type_key",
        user_id
    )
    await conn.close()
    total = 0
    by_mode = {}
    for row in rows:
        total += row["cnt"]
        by_mode[row["type_key"]] = row["cnt"]
    return {"total": total, "by_mode": by_mode}

async def reset_full_progress(user_id: int):
    """Полный сброс (удаляет всё, кроме users)"""
    conn = await get_connection()
    await conn.execute("DELETE FROM progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM errors WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM grammar_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM writing_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM govorenie_progress WHERE user_id = $1", user_id)
    await conn.close()

# ---------- Клавиатуры ----------

def get_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔧 Работа над ошибками", callback_data="profile_fix_mistakes")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="profile_settings")],
        [InlineKeyboardButton(text="💳 Подписка", callback_data="profile_subscription")],
        [InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="profile_reset_confirm")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_settings_keyboard(notif_on: bool, time_str: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔔 Уведомления: {'Вкл' if notif_on else 'Выкл'}", callback_data="profile_notif_toggle"),
         InlineKeyboardButton(text=f"⏰ Время: {time_str}", callback_data="profile_notif_time")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")]
    ])

def get_subscription_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="profile_extend")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")]
    ])

# ---------- Обработчики ----------

@router.callback_query(lambda c: c.data == "profile_menu")
async def profile_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    await update_last_active(user_id)

    profile = await get_user_profile(user_id)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    streak = await calculate_streak(user_id)

    # Уровень (заглушка)
    level = "A2"
    next_level = "B1"
    progress_to_next = 75

    # Сбор статистики
    skills = {}
    for mode in ["grammar", "listening", "reading", "lexis"]:
        data = await get_progress_summary(user_id, mode)
        if data["total"] > 0:
            skills[mode] = {"percent": data["percent"], "correct": data["correct"], "total": data["total"]}

    writing = await get_writing_summary(user_id)
    if writing["answered"] > 0:
        skills["writing"] = {"avg": writing["avg"], "checks": writing["answered"]}

    speaking = await get_speaking_summary(user_id)
    if speaking["answered"] > 0:
        skills["speaking"] = {"avg": speaking["avg"], "checks": speaking["answered"]}

    # Активность (AI и ролевые игры – пока нет данных)
    ai_messages = 0
    role_started = 0
    role_completed = 0

    mistakes = await count_user_errors(user_id)
    total_mistakes = mistakes["total"]
    by_mode = mistakes["by_mode"]

    # Слабое место
    weak_skill = None
    weak_percent = 100
    for mode, data in skills.items():
        if "percent" in data and data["percent"] < weak_percent:
            weak_percent = data["percent"]
            weak_skill = mode
    if weak_skill is None:
        for mode in ["writing", "speaking"]:
            if mode in skills and skills[mode].get("avg", 0) < 3.0:
                weak_skill = mode
                break

    # Формируем текст
    text = f"🔥 Серия: {streak} дней\n"
    text += f"📊 Ваш уровень: {level} — прогресс {progress_to_next}% до {next_level}\n\n"
    text += "📈 Навыки (общий прогресс):\n"

    for mode, data in skills.items():
        if "percent" in data:
            p = data["percent"]
            bar = "█" * (p // 10) + "░" * (10 - p // 10)
            emoji = "✅" if p >= 80 else "⚠️" if p < 50 else "📖"
            label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика"}.get(mode, mode.capitalize())
            text += f"{label}: {bar} {p}% {emoji}\n"

    for mode in ["writing", "speaking"]:
        if mode in skills:
            avg = skills[mode]["avg"]
            checks = skills[mode]["checks"]
            label = "Письмо" if mode == "writing" else "Говорение"
            emoji = "🖊️" if mode == "writing" else "🎤"
            text += f"{emoji} {label}: {avg} / 5.0  (проверок: {checks})\n"

    text += "\n💬 Активность:\n"
    text += f"🗣️ Общение с AI: {ai_messages} сообщений\n"
    if role_started > 0:
        text += f"🎭 Ролевые игры: пройдено {role_completed} из {role_started} сценариев\n"

    if total_mistakes > 0:
        text += f"\n⚠️ ВАЖНО: У вас {total_mistakes} ошибок ждут исправления!\n"
        if by_mode:
            parts = []
            for m, cnt in by_mode.items():
                label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика", "writing": "Письмо", "speaking": "Говорение"}.get(m, m.capitalize())
                parts.append(f"{label}: {cnt}")
            text += "   (" + ", ".join(parts) + ")\n"
    else:
        text += "\n✅ Ошибок для исправления нет! Отлично!\n"

    if weak_skill:
        advice = ""
        if weak_skill in ["grammar", "listening", "reading", "lexis"]:
            advice = f"Вам нужно подтянуть { {'grammar':'Грамматику','listening':'Аудирование','reading':'Чтение','lexis':'Лексику'}.get(weak_skill, weak_skill)}. Пройдите тренажёр или исправьте ошибки!"
        elif weak_skill in ["writing", "speaking"]:
            advice = f"Ваш средний балл по { {'writing':'Письму','speaking':'Говорению'}.get(weak_skill, weak_skill)} низкий. Практикуйтесь больше!"
        if advice:
            text += f"\n💡 Совет: {advice}"

    # Подписка
    sub_end = profile.get("subscription_end", 0)
    if sub_end and sub_end > int(datetime.now().timestamp()):
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        text += f"\n\n💳 Подписка активна до {expires}"
    else:
        text += "\n\n💳 Подписка не активна"

    await callback.message.edit_text(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_fix_mistakes")
async def profile_fix_mistakes(callback: CallbackQuery):
    user_id = callback.from_user.id
    mistakes = await count_user_errors(user_id)
    if mistakes["total"] == 0:
        await callback.answer("У вас нет ошибок для исправления!", show_alert=True)
        return
    text = "🔧 <b>Работа над ошибками</b>\n\nВыберите режим:\n"
    buttons = []
    for mode, cnt in mistakes["by_mode"].items():
        label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика", "writing": "Письмо", "speaking": "Говорение"}.get(mode, mode.capitalize())
        buttons.append([InlineKeyboardButton(text=f"{label} ({cnt})", callback_data=f"fix_{mode}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("fix_"))
async def fix_mode_callback(callback: CallbackQuery):
    mode = callback.data.split("_")[1]
    await callback.answer(f"Исправление ошибок в {mode} (в разработке)", show_alert=True)

@router.callback_query(lambda c: c.data == "profile_settings")
async def profile_settings(callback: CallbackQuery):
    # Заглушка – позже добавим таблицу настроек
    keyboard = get_settings_keyboard(True, "10:00")
    await callback.message.edit_text("⚙️ <b>Настройки</b>\n\nУправляйте уведомлениями и временем.", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_notif_toggle")
async def profile_notif_toggle(callback: CallbackQuery):
    await callback.answer("Функция уведомлений в разработке.", show_alert=True)
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_notif_time")
async def profile_notif_time(callback: CallbackQuery):
    await callback.answer("Настройка времени – в разработке.", show_alert=True)
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_subscription")
async def profile_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    profile = await get_user_profile(user_id)
    sub_end = profile.get("subscription_end", 0) if profile else 0
    if sub_end and sub_end > int(datetime.now().timestamp()):
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        text = f"💳 <b>Подписка активна</b>\n\nДата окончания: {expires}"
    else:
        text = "💳 <b>Подписка не активна</b>\n\nОформите подписку для полного доступа."
    await callback.message.edit_text(text, reply_markup=get_subscription_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_extend")
async def profile_extend(callback: CallbackQuery):
    await callback.message.answer("💳 Функция продления подписки будет доступна позже.\nСвяжитесь с поддержкой.")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_reset_confirm")
async def profile_reset_confirm(callback: CallbackQuery):
    text = (
        "⚠️ <b>Внимание!</b>\n\n"
        "Вы действительно хотите сбросить весь прогресс?\n"
        "Будут удалены все данные по грамматике, аудированию, чтению, лексике, письму и говорению.\n"
        "Прогресс в общении с AI и ролевых играх не сбрасывается.\n\n"
        "Это действие нельзя отменить.\n\n"
        "Введите слово <b>СБРОС</b> в поле для сообщения, чтобы подтвердить."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="profile_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(F.text)
async def profile_reset_handle(message: Message):
    if message.text.strip().upper() == "СБРОС":
        user_id = message.from_user.id
        await reset_full_progress(user_id)
        await message.answer("✅ Прогресс успешно сброшен. Вы начинаете с чистого листа.")
        await show_main_menu(message, edit=False)
    # иначе игнорируем

@router.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: CallbackQuery):
    await show_main_menu(callback.message, edit=True)
    await callback.answer()