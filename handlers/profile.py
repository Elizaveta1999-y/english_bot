from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import asyncio

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

# ---------- Таблица глобальной статистики ----------

async def ensure_stats_table():
    conn = await get_connection()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id BIGINT PRIMARY KEY,
            lessons_completed INTEGER DEFAULT 0,
            practices_completed INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            wrong_answers INTEGER DEFAULT 0
        )
    """)
    await conn.close()

# ---------- Асинхронные функции обновления ----------

async def _update_stats_after_lesson(user_id: int):
    await ensure_stats_table()
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO user_stats (user_id, lessons_completed) VALUES ($1, 1)
        ON CONFLICT (user_id) DO UPDATE SET lessons_completed = user_stats.lessons_completed + 1
    """, user_id)
    await conn.close()
    conn = await get_connection()
    await conn.execute(
        "UPDATE users SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT WHERE user_id = $1",
        user_id
    )
    await conn.close()

async def _update_stats_after_practice(user_id: int, correct: int, wrong: int):
    await ensure_stats_table()
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO user_stats (user_id, practices_completed, correct_answers, wrong_answers)
        VALUES ($1, 1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE SET
            practices_completed = user_stats.practices_completed + 1,
            correct_answers = user_stats.correct_answers + $2,
            wrong_answers = user_stats.wrong_answers + $3
    """, user_id, correct, wrong)
    await conn.close()
    conn = await get_connection()
    await conn.execute(
        "UPDATE users SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT WHERE user_id = $1",
        user_id
    )
    await conn.close()

# ---------- Синхронные обёртки для обратной совместимости ----------

def update_stats_after_lesson(user_id: int):
    asyncio.run(_update_stats_after_lesson(user_id))

def update_stats_after_practice(user_id: int, correct: int, wrong: int):
    asyncio.run(_update_stats_after_practice(user_id, correct, wrong))

# ---------- Вспомогательные функции для профиля ----------

async def get_user_profile(user_id: int):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return dict(row) if row else None

async def update_last_active(user_id: int):
    conn = await get_connection()
    await conn.execute(
        "UPDATE users SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT WHERE user_id = $1",
        user_id
    )
    await conn.close()

async def calculate_streak(user_id: int) -> int:
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
        return 1
    else:
        return 0

async def get_progress_summary(user_id: int, type_key: str) -> dict:
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
    """
    Возвращает общее количество ошибок и группировку по основному режиму
    (первая часть до подчёркивания в type_key).
    """
    conn = await get_connection()
    rows = await conn.fetch(
        "SELECT type_key, COUNT(*) as cnt FROM errors WHERE user_id = $1 GROUP BY type_key",
        user_id
    )
    await conn.close()
    total = 0
    by_mode = {}
    for row in rows:
        raw_key = row["type_key"]
        # Извлекаем основной режим (до первого '_')
        if '_' in raw_key:
            mode = raw_key.split('_')[0]
        else:
            mode = raw_key
        by_mode[mode] = by_mode.get(mode, 0) + row["cnt"]
        total += row["cnt"]
    return {"total": total, "by_mode": by_mode}

async def reset_full_progress(user_id: int):
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
        # Если профиля нет, создаём его
        await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name, callback.from_user.last_name)
        profile = await get_user_profile(user_id)
        if not profile:
            await callback.answer("Ошибка создания профиля", show_alert=True)
            return

    streak = await calculate_streak(user_id)

    # Уровень (вычисляем по количеству правильных ответов, например)
    # Соберём все правильные ответы из тренажёров и письма/говорения
    total_correct = 0
    for mode in ["grammar", "listening", "reading", "lexis"]:
        data = await get_progress_summary(user_id, mode)
        total_correct += data["correct"]
    writing = await get_writing_summary(user_id)
    total_correct += writing.get("score_sum", 0)  # для письма баллы считаем как правильные
    speaking = await get_speaking_summary(user_id)
    total_correct += speaking.get("score_sum", 0)

    # Условный уровень (пример)
    if total_correct < 50:
        level = "A1"
        next_level = "A2"
        progress_to_next = round(total_correct / 50 * 100)
    elif total_correct < 150:
        level = "A2"
        next_level = "B1"
        progress_to_next = round((total_correct - 50) / 100 * 100)
    elif total_correct < 300:
        level = "B1"
        next_level = "B2"
        progress_to_next = round((total_correct - 150) / 150 * 100)
    else:
        level = "B2"
        next_level = "C1"
        progress_to_next = round((total_correct - 300) / 200 * 100)

    # Сбор статистики по тренажёрам
    skills = {}
    for mode in ["grammar", "listening", "reading", "lexis"]:
        data = await get_progress_summary(user_id, mode)
        skills[mode] = {"percent": data["percent"], "correct": data["correct"], "total": data["total"]}

    # Продуктивные навыки
    writing = await get_writing_summary(user_id)
    if writing["answered"] > 0:
        skills["writing"] = {"avg": writing["avg"], "checks": writing["answered"], "score_sum": writing["score_sum"]}

    speaking = await get_speaking_summary(user_id)
    if speaking["answered"] > 0:
        skills["speaking"] = {"avg": speaking["avg"], "checks": speaking["answered"], "score_sum": speaking["score_sum"]}

    # Активность (пока нет данных, заглушки)
    ai_messages = 0
    ai_duration = 0
    role_started = 0
    role_completed = 0

    mistakes = await count_user_errors(user_id)
    total_mistakes = mistakes["total"]
    by_mode = mistakes["by_mode"]

    # Определяем слабое место (среди тренажёров)
    weak_skill = None
    weak_percent = 100
    for mode, data in skills.items():
        if "percent" in data and data["total"] > 0 and data["percent"] < weak_percent:
            weak_percent = data["percent"]
            weak_skill = mode
    # Если нет данных по тренажёрам, смотрим продуктивные
    if weak_skill is None:
        for mode in ["writing", "speaking"]:
            if mode in skills and skills[mode].get("avg", 0) < 3.0:
                weak_skill = mode
                break

    # Формируем текст
    text = f"🔥 Серия: {streak} дней\n"
    text += f"📊 Ваш уровень: {level} — прогресс {min(progress_to_next, 100)}% до {next_level}\n\n"

    # Тренажёры (точность ответов)
    text += "📊 Тренажеры (точность ответов):\n"
    for mode in ["grammar", "listening", "reading", "lexis"]:
        data = skills.get(mode, {})
        percent = data.get("percent", 0)
        total = data.get("total", 0)
        bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
        emoji = "✅" if percent >= 80 else "⚠️" if percent < 50 else "📖"
        label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика"}.get(mode, mode.capitalize())
        # Добавим слабое место, если есть данные и процент низкий
        weak_info = ""
        if mode == weak_skill and total > 0:
            weak_info = " ⚠️ Слабое место!"
        text += f"{label}: {bar} {percent}% {emoji}{weak_info}\n"

    # Продуктивные навыки (средний балл)
    text += "\n✍️ Продуктивные навыки (средний балл):\n"
    for mode in ["writing", "speaking"]:
        if mode in skills:
            avg = skills[mode]["avg"]
            checks = skills[mode]["checks"]
            label = "Письмо" if mode == "writing" else "Говорение"
            emoji = "🖊️" if mode == "writing" else "🎤"
            # Вычисляем динамику (заглушка)
            trend = "↗️" if avg > 3.5 else "↘️" if avg < 3.0 else "➡️"
            text += f"{emoji} {label}: {avg} / 5.0  (проверок: {checks}) {trend}\n"
        else:
            label = "Письмо" if mode == "writing" else "Говорение"
            emoji = "🖊️" if mode == "writing" else "🎤"
            text += f"{emoji} {label}: нет данных\n"

    # Активность
    text += "\n💬 Активность:\n"
    if ai_messages > 0:
        text += f"🗣️ Общение с AI: {ai_messages} сообщений (≈ {ai_duration} минут диалогов)\n"
    else:
        text += "🗣️ Общение с AI: пока нет данных\n"
    if role_started > 0:
        text += f"🎭 Ролевые игры: пройдено {role_completed} из {role_started} сценариев\n"
    else:
        text += "🎭 Ролевые игры: пока нет данных\n"

    # Ошибки
    if total_mistakes > 0:
        text += f"\n⚠️ ВАЖНО: У вас {total_mistakes} ошибок ждут исправления!\n"
        if by_mode:
            parts = []
            for mode, cnt in by_mode.items():
                # Человеческое название режима
                label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика", "writing": "Письмо", "speaking": "Говорение"}.get(mode, mode.capitalize())
                parts.append(f"{label}: {cnt}")
            text += "   (" + " | ".join(parts) + ")\n"
    else:
        text += "\n✅ Ошибок для исправления нет! Отлично!\n"

    # Совет
    if weak_skill:
        advice = ""
        if weak_skill in ["grammar", "listening", "reading", "lexis"]:
            advice = f"Вам нужно подтянуть { {'grammar':'Грамматику','listening':'Аудирование','reading':'Чтение','lexis':'Лексику'}.get(weak_skill, weak_skill)}. Пройдите тренажёр!"
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

@router.callback_query(lambda c: c.data == "profile_settings")
async def profile_settings(callback: CallbackQuery):
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

@router.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: CallbackQuery):
    await show_main_menu(callback.message, edit=True)
    await callback.answer()