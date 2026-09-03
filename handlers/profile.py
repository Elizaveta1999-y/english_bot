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
    clear_bonus_notification,
    get_bonus_notification,
    get_user_profile,
)

from handlers.subscription import show_subscription

logger = logging.getLogger(__name__)
router = Router()

READING_TYPE_KEYS = [
    "Подбор_заголовка",
    "True_False_Not_stated",
    "Вопросы_с_выбором_ответа",
    "Восстановление_порядка_абзацев"
]

async def get_progress_summary_for_keys(user_id: int, type_keys: list) -> dict:
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
    return await get_progress_summary_for_keys(user_id, READING_TYPE_KEYS)

async def get_lexis_summary(user_id: int) -> dict:
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

async def get_listening_summary(user_id: int) -> dict:
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT COALESCE(SUM(correct), 0) as correct, COALESCE(SUM(wrong), 0) as wrong FROM progress WHERE user_id = $1 AND type_key LIKE 'listening_%'",
        user_id
    )
    await conn.close()
    correct = row["correct"] if row else 0
    wrong = row["wrong"] if row else 0
    total = correct + wrong
    percent = round((correct / total * 100)) if total else 0
    return {"correct": correct, "wrong": wrong, "total": total, "percent": percent}

async def get_writing_summary(user_id: int) -> dict:
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
        # Чтение: проверяем по конкретным ключам
        if raw_key in ("Подбор_заголовка", "True_False_Not_stated", "Вопросы_с_выбором_ответа", "Восстановление_порядка_абзацев"):
            mode = "reading"
        elif raw_key.startswith("grammar_"):
            mode = "grammar"
        elif raw_key.startswith("words_"):
            mode = "lexis"
        elif raw_key.startswith("listening_"):
            mode = "listening"
        elif raw_key.startswith("reading_"):
            mode = "reading"
        else:
            mode = "reading"  # запасной вариант
        by_mode[mode] = by_mode.get(mode, 0) + row["cnt"]
        total += row["cnt"]
    return {"total": total, "by_mode": by_mode}

async def update_last_active(user_id: int):
    conn = await get_connection()
    await conn.execute(
        "UPDATE users SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT WHERE user_id = $1",
        user_id
    )
    await conn.close()

async def reset_full_progress(user_id: int):
    conn = await get_connection()
    await conn.execute("DELETE FROM progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM errors WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM grammar_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM writing_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM govorenie_progress WHERE user_id = $1", user_id)
    await conn.close()

def get_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
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

async def safe_edit_message(message, text, reply_markup=None, parse_mode="HTML"):
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            logger.debug("Сообщение не изменилось, пропускаем редактирование")
        else:
            raise

@router.callback_query(lambda c: c.data == "profile_menu")
async def profile_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    await update_last_active(user_id)

    profile = await get_user_profile(user_id)
    if not profile:
        username = getattr(callback.from_user, 'username', None)
        first_name = getattr(callback.from_user, 'first_name', None)
        last_name = getattr(callback.from_user, 'last_name', None)
        await get_or_create_user(user_id, username, first_name, last_name)
        profile = await get_user_profile(user_id)
        if not profile:
            try:
                await callback.answer("Ошибка создания профиля", show_alert=True)
            except Exception:
                pass
            return

    show_bonus, bonus_reason = await get_bonus_notification(user_id)
    bonus_message = ""
    if show_bonus:
        sub_end = profile.get("subscription_until", 0)
        if sub_end:
            expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
            bonus_message = (
                f"🎉 Тебе начислены бонусные дни!\n"
                f"Твоя подписка продлена до {expires}.\n"
                f"{bonus_reason}\n\n"
            )
        else:
            bonus_message = (
                f"🎉 Тебе начислены бонусные дни!\n"
                f"{bonus_reason}\n\n"
            )
        await clear_bonus_notification(user_id)

    grammar_data = await get_grammar_summary(user_id)
    reading_data = await get_reading_summary(user_id)
    lexis_data = await get_lexis_summary(user_id)
    listening_data = await get_listening_summary(user_id)
    writing_data = await get_writing_summary(user_id)
    speaking_data = await get_speaking_summary(user_id)
    mistakes = await count_user_errors(user_id)

    text = bonus_message

    # ===== ТРЕНАЖЁРЫ =====
    text += "<b>• Тренажёры</b>\n"
    text += "Точность ответов:\n"

    pct = grammar_data["percent"]
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    text += f"🔀 Грамматика {pct}%\n"
    text += f"{bar}\n"

    pct = reading_data["percent"]
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    text += f"📖 Чтение {pct}%\n"
    text += f"{bar}\n"

    pct = lexis_data["percent"]
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    text += f"🥇 Лексика {pct}%\n"
    text += f"{bar}\n"

    pct = listening_data["percent"]
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    text += f"🔉 Аудирование {pct}%\n"
    text += f"{bar}\n"

    # ===== ПРОДУКТИВНЫЕ НАВЫКИ =====
    text += "\n<b>• Продуктивные навыки</b>\n"
    text += "Средний балл:\n"

    if writing_data["answered"] > 0:
        avg = writing_data["avg"]
        text += f"📝 Письмо    {avg} / 5.0  ({writing_data['answered']} работ)\n"
    else:
        text += "📝 Письмо    — нет данных\n"

    if speaking_data["answered"] > 0:
        avg = speaking_data["avg"]
        text += f"🗣️ Говорение  {avg} / 5.0  ({speaking_data['answered']} работ)\n"
    else:
        text += "🗣️ Говорение  — нет данных\n"

    # ===== ОШИБКИ (всегда 4 режима) =====
    total_mistakes = mistakes["total"]
    by_mode = mistakes["by_mode"]

    text += "\n<b>• Ошибки</b>\n"
    if total_mistakes > 0:
        text += f"Всего: {total_mistakes}\n"
        mode_labels = {
            "grammar": "🔀 Грамматика",
            "lexis": "🥇 Лексика",
            "listening": "🔉 Аудирование",
            "reading": "📖 Чтение"
        }
        for mode in ["grammar", "lexis", "listening", "reading"]:
            count = by_mode.get(mode, 0)
            text += f"• {mode_labels[mode]}: {count}\n"
    else:
        text += "Нет данных\n"

    # ===== ПОДПИСКА =====
    text += "\n💳 Подписка: "
    sub_end = profile.get("subscription_until", 0)
    if sub_end and sub_end > int(datetime.now().timestamp()):
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        text += f"активна до {expires}"
    else:
        text += "не активна"

    await safe_edit_message(
        callback.message,
        text,
        reply_markup=get_profile_keyboard(),
        parse_mode="HTML"
    )
    try:
        await callback.answer()
    except Exception:
        pass

@router.callback_query(lambda c: c.data == "profile_settings")
async def profile_settings(callback: CallbackQuery):
    keyboard = get_settings_keyboard(True, "10:00")
    await safe_edit_message(
        callback.message,
        "⚙️ <b>Настройки</b>\n\nУправляйте уведомлениями и временем.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    try:
        await callback.answer()
    except Exception:
        pass

@router.callback_query(lambda c: c.data == "profile_notif_toggle")
async def profile_notif_toggle(callback: CallbackQuery):
    try:
        await callback.answer("Функция уведомлений в разработке.", show_alert=True)
    except Exception:
        pass
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_notif_time")
async def profile_notif_time(callback: CallbackQuery):
    try:
        await callback.answer("Настройка времени – в разработке.", show_alert=True)
    except Exception:
        pass
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_subscription")
async def profile_subscription(callback: CallbackQuery):
    await show_subscription(callback.message, callback.from_user.id)

@router.callback_query(lambda c: c.data == "profile_extend")
async def profile_extend(callback: CallbackQuery):
    await callback.message.answer("💳 Функция продления подписки будет доступна позже.\nСвяжитесь с поддержкой.")
    try:
        await callback.answer()
    except Exception:
        pass

@router.callback_query(lambda c: c.data == "profile_reset_confirm")
async def profile_reset_confirm(callback: CallbackQuery):
    text = (
        "⚠️ <b>Внимание!</b>\n\n"
        "Вы действительно хотите сбросить весь прогресс?\n"
        "Будут удалены все данные по тренажёрам и продуктивным навыкам.\n"
        "Это действие нельзя отменить.\n\n"
        "Введите слово <b>СБРОС</b> для подтверждения."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="profile_back")]
    ])
    await safe_edit_message(
        callback.message,
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    try:
        await callback.answer()
    except Exception:
        pass

@router.message(F.text, ~F.text.in_({"📊 Я всё! Фидбек", "🏠 Главное меню"}))
async def profile_reset_handle(message: Message):
    if message.text.strip().upper() == "СБРОС":
        user_id = message.from_user.id
        await reset_full_progress(user_id)
        await message.answer("✔️ Прогресс успешно сброшен.")
        from handlers.start import show_main_menu
        await show_main_menu(message, edit=False)

@router.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: CallbackQuery):
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    try:
        await callback.answer()
    except Exception:
        pass

async def show_profile(message, user_id: int, edit: bool = False):
    class FakeCallback:
        def __init__(self, message, user_id):
            self.message = message
            self.from_user = type('obj', (object,), {
                'id': user_id,
                'username': None,
                'first_name': None,
                'last_name': None
            })()
        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallback(message, user_id)
    await profile_menu(fake_callback)

# =====================================================================
# ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СОВМЕСТИМОСТИ С ДРУГИМИ МОДУЛЯМИ
# =====================================================================

async def _update_stats_after_lesson(user_id: int):
    pass

async def _update_stats_after_practice(user_id: int, correct: int, wrong: int):
    pass

def update_stats_after_lesson(user_id: int):
    asyncio.run(_update_stats_after_lesson(user_id))

def update_stats_after_practice(user_id: int, correct: int, wrong: int):
    asyncio.run(_update_stats_after_practice(user_id, correct, wrong))