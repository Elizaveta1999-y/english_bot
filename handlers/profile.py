from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import asyncio
import logging

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

logger = logging.getLogger(__name__)
router = Router()

# ---------- Константы для ключей чтения (из TYPE_MAP в reading.py) ----------
READING_TYPE_KEYS = [
    "Подбор_заголовка",
    "True_False_Not_stated",
    "Вопросы_с_выбором_ответа",
    "Восстановление_порядка_абзацев"
]

# ---------- Функции для сбора статистики из PostgreSQL ----------

async def get_progress_summary_for_keys(user_id: int, type_keys: list) -> dict:
    """Суммирует correct и wrong по всем переданным type_key."""
    if not type_keys:
        return {"correct": 0, "wrong": 0, "total": 0, "percent": 0}
    conn = await get_connection()
    placeholders = ','.join([f"${i+2}" for i in range(len(type_keys))])
    query = f"""
        SELECT COALESCE(SUM(correct), 0) as correct, COALESCE(SUM(wrong), 0) as wrong
        FROM progress
        WHERE user_id = $1 AND type_key IN ({placeholders})
    """
    row = await conn.fetchrow(query, user_id, *type_keys)
    await conn.close()
    correct = row["correct"] if row else 0
    wrong = row["wrong"] if row else 0
    total = correct + wrong
    percent = round((correct / total * 100)) if total else 0
    return {"correct": correct, "wrong": wrong, "total": total, "percent": percent}

async def get_grammar_summary(user_id: int) -> dict:
    """Суммирует все ключи, начинающиеся с 'grammar_'."""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT COALESCE(SUM(correct), 0) as correct, COALESCE(SUM(wrong), 0) as wrong FROM progress WHERE user_id = $1 AND type_key LIKE 'grammar_%'",
        user_id
    )
    await conn.close()
    correct = row["correct"] if row else 0
    wrong = row["wrong"] if row else 0
    total = correct + wrong
    percent = round((correct / total * 100)) if total else 0
    return {"correct": correct, "wrong": wrong, "total": total, "percent": percent}

async def get_reading_summary(user_id: int) -> dict:
    """Суммирует ключи из READING_TYPE_KEYS."""
    return await get_progress_summary_for_keys(user_id, READING_TYPE_KEYS)

async def get_lexis_summary(user_id: int) -> dict:
    """Суммирует все ключи, начинающиеся с 'words_'."""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT COALESCE(SUM(correct), 0) as correct, COALESCE(SUM(wrong), 0) as wrong FROM progress WHERE user_id = $1 AND type_key LIKE 'words_%'",
        user_id
    )
    await conn.close()
    correct = row["correct"] if row else 0
    wrong = row["wrong"] if row else 0
    total = correct + wrong
    percent = round((correct / total * 100)) if total else 0
    return {"correct": correct, "wrong": wrong, "total": total, "percent": percent}

async def get_writing_summary(user_id: int) -> dict:
    """Суммирует данные из writing_progress."""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT COALESCE(SUM(total_answered), 0) as answered, COALESCE(SUM(total_score), 0) as score_sum FROM writing_progress WHERE user_id = $1",
        user_id
    )
    await conn.close()
    answered = row["answered"] if row else 0
    score_sum = row["score_sum"] if row else 0
    avg = round(score_sum / answered, 1) if answered else 0.0
    return {"answered": answered, "score_sum": score_sum, "avg": avg}

async def get_speaking_summary(user_id: int) -> dict:
    """Суммирует данные из govorenie_progress."""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT COALESCE(SUM(total_answered), 0) as answered, COALESCE(SUM(total_score), 0) as score_sum FROM govorenie_progress WHERE user_id = $1",
        user_id
    )
    await conn.close()
    answered = row["answered"] if row else 0
    score_sum = row["score_sum"] if row else 0
    avg = round(score_sum / answered, 1) if answered else 0.0
    return {"answered": answered, "score_sum": score_sum, "avg": avg}

async def count_user_errors(user_id: int) -> dict:
    """Считает ошибки из таблицы errors, группируя по основному режиму (до первого '_')."""
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
        if '_' in raw_key:
            mode = raw_key.split('_')[0]
        else:
            mode = raw_key
        by_mode[mode] = by_mode.get(mode, 0) + row["cnt"]
        total += row["cnt"]
    return {"total": total, "by_mode": by_mode}

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

async def reset_full_progress(user_id: int):
    conn = await get_connection()
    await conn.execute("DELETE FROM progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM errors WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM grammar_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM writing_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM govorenie_progress WHERE user_id = $1", user_id)
    await conn.close()

# ---------- Функции для обновления статистики (для совместимости с other handlers) ----------

async def _update_stats_after_lesson(user_id: int):
    # Пока заглушка, т.к. неясно, что считать "уроком"
    pass

async def _update_stats_after_practice(user_id: int, correct: int, wrong: int):
    # Пока заглушка
    pass

def update_stats_after_lesson(user_id: int):
    asyncio.run(_update_stats_after_lesson(user_id))

def update_stats_after_practice(user_id: int, correct: int, wrong: int):
    asyncio.run(_update_stats_after_practice(user_id, correct, wrong))

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

def get_confirm_reset_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="profile_reset_do")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="profile_back")]
    ])

# ---------- Обработчик главного меню статистики ----------

@router.callback_query(lambda c: c.data == "profile_menu")
async def profile_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    await update_last_active(user_id)

    # Убедимся, что пользователь есть в БД
    profile = await get_user_profile(user_id)
    if not profile:
        await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name, callback.from_user.last_name)
        profile = await get_user_profile(user_id)
        if not profile:
            await callback.answer("Ошибка создания профиля", show_alert=True)
            return

    streak = await calculate_streak(user_id)

    # Сбор статистики
    skills = {}
    any_data = False

    # Грамматика
    grammar_data = await get_grammar_summary(user_id)
    if grammar_data["total"] > 0:
        any_data = True
        skills["grammar"] = {"percent": grammar_data["percent"], "correct": grammar_data["correct"], "total": grammar_data["total"]}

    # Аудирование - пока нет данных из PostgreSQL (используется Redis)
    # Пока оставляем заглушку "нет данных"
    # В будущем можно будет добавить сбор из Redis

    # Чтение
    reading_data = await get_reading_summary(user_id)
    if reading_data["total"] > 0:
        any_data = True
        skills["reading"] = {"percent": reading_data["percent"], "correct": reading_data["correct"], "total": reading_data["total"]}

    # Лексика
    lexis_data = await get_lexis_summary(user_id)
    if lexis_data["total"] > 0:
        any_data = True
        skills["lexis"] = {"percent": lexis_data["percent"], "correct": lexis_data["correct"], "total": lexis_data["total"]}

    # Письмо
    writing = await get_writing_summary(user_id)
    if writing["answered"] > 0:
        any_data = True
        skills["writing"] = {"avg": writing["avg"], "checks": writing["answered"]}

    # Говорение
    speaking = await get_speaking_summary(user_id)
    if speaking["answered"] > 0:
        any_data = True
        skills["speaking"] = {"avg": speaking["avg"], "checks": speaking["answered"]}

    # Ошибки
    mistakes = await count_user_errors(user_id)
    total_mistakes = mistakes["total"]
    by_mode = mistakes["by_mode"]

    # Определяем самый слабый навык
    weak_skill = None
    weak_value = 100
    # Проверяем тренажёры
    for mode in ["grammar", "reading", "lexis"]:
        if mode in skills and skills[mode].get("total", 0) > 0:
            pct = skills[mode].get("percent", 0)
            if pct < weak_value:
                weak_value = pct
                weak_skill = mode
    # Проверяем продуктивные
    for mode in ["writing", "speaking"]:
        if mode in skills and skills[mode].get("checks", 0) > 0:
            avg = skills[mode].get("avg", 5)
            if avg < 3.5 and avg < weak_value:
                weak_value = avg
                weak_skill = mode

    # ---------- Формирование текста (первый вариант) ----------
    text = f"🔥 Серия: {streak} день" + ("ей" if streak > 1 else "")
    text += f"\n⏱️ Время занятий: 0 мин\n\n"

    # Тренажёры
    text += "▸ Тренажёры (точность ответов):\n"
    for mode, label in [("grammar", "Грамматика"), ("reading", "Чтение"), ("lexis", "Лексика")]:
        data = skills.get(mode, {})
        percent = data.get("percent", 0)
        total = data.get("total", 0)
        if total > 0:
            bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
            emoji = " ⚠️" if percent < 50 else ""
            text += f"  {label}   {bar} {percent}%{emoji}\n"
        else:
            text += f"  {label}   нет данных\n"
    # Аудирование пока нет данных
    text += "  Аудирование   нет данных\n"

    # Продуктивные навыки
    text += "\n▸ Продуктивные навыки (средний балл):\n"
    for mode, label in [("writing", "Письмо"), ("speaking", "Говорение")]:
        if mode in skills and skills[mode].get("checks", 0) > 0:
            avg = skills[mode]["avg"]
            checks = skills[mode]["checks"]
            text += f"  {label}   {avg} / 5.0 ({checks} работ)\n"
        else:
            text += f"  {label}   нет данных\n"

    # Активность (заглушки)
    text += "\n▸ Активность:\n"
    text += "  Общение с AI: пока нет данных\n"
    text += "  Ролевые игры: пока нет данных\n"

    # Ошибки
    if total_mistakes > 0:
        text += f"\n⚠️ Ошибки: {total_mistakes}"
        if by_mode:
            parts = []
            for mode, cnt in by_mode.items():
                label = {"grammar": "Грамматика", "reading": "Чтение", "lexis": "Лексика", "writing": "Письмо", "speaking": "Говорение"}.get(mode, mode.capitalize())
                parts.append(f"{label}:{cnt}")
            text += " (" + " | ".join(parts) + ")"
        text += "\n"
    else:
        text += "\n✅ Ошибок нет\n"

    # Совет
    if not any_data:
        advice = "Начните с любого тренажёра."
    elif weak_skill is None:
        advice = "Отличный прогресс! Так держать."
    else:
        advice_map = {
            "grammar": "Повторите правила и пройдите тренажёр.",
            "reading": "Читайте тексты каждый день.",
            "lexis": "Учите новые слова регулярно.",
            "writing": "Больше практикуйтесь в письме.",
            "speaking": "Говорите чаще, не бойтесь ошибок."
        }
        advice = advice_map.get(weak_skill, "Продолжайте заниматься.")
        if weak_skill in ["writing", "speaking"] and weak_value >= 3.5:
            advice = "Отличный прогресс! Так держать."

    if total_mistakes > 10:
        advice += " Также у вас много ошибок — повторите задания, в которых ошиблись."

    text += f"\n💡 Совет: {advice}\n"

    # Подписка
    sub_end = profile.get("subscription_end", 0)
    if sub_end and sub_end > int(datetime.now().timestamp()):
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        text += f"\n💳 Подписка: активна до {expires}"
    else:
        text += "\n💳 Подписка: не активна"

    await callback.message.edit_text(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    await callback.answer()

# ---------- Остальные обработчики (Настройки, Подписка, Сброс, Назад) ----------

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
        "Будут удалены все данные по тренажёрам и продуктивным навыкам.\n"
        "Прогресс в общении с AI и ролевых играх не сбрасывается.\n\n"
        "Это действие нельзя отменить.\n\n"
        "Введите слово <b>СБРОС</b> для подтверждения."
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
        await message.answer("✅ Прогресс успешно сброшен.")
        await show_main_menu(message, edit=False)

@router.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: CallbackQuery):
    await show_main_menu(callback.message, edit=True)
    await callback.answer()