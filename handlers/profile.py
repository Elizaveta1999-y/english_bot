# handlers/profile.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import asyncpg
from data.db import (
    get_connection, get_user_stats_db, reset_user_stats_db,
    get_writing_progress, get_govorenie_progress,
    reset_writing_progress, reset_govorenie_progress,
    clear_reading_errors_db, reset_grammar_progress,
    reset_all_user_progress  # для полного сброса
)
from handlers.start import show_main_menu

router = Router()

# ---------- Вспомогательные функции работы с БД ----------

async def get_user_profile(user_id: int):
    """Возвращает данные пользователя из таблицы users"""
    conn = await get_connection()
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return dict(row) if row else None

async def update_last_active(user_id: int):
    """Обновляет время последней активности (для серии)"""
    conn = await get_connection()
    await conn.execute(
        "UPDATE users SET last_active = EXTRACT(EPOCH FROM NOW())::BIGINT WHERE user_id = $1",
        user_id
    )
    await conn.close()

async def calculate_streak(user_id: int) -> int:
    """
    Вычисляет текущую серию (количество дней подряд, когда была активность).
    Использует поле last_active (Unix timestamp) в таблице users.
    Если прошло менее 2 дней с последней активности — серия продолжается,
    если ровно 1 день — увеличивается, если больше — сбрасывается до 1 (если активность сегодня).
    """
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
        # сегодня уже активность — не меняем, но нужно вернуть текущую серию (если храним)
        # Мы не храним серию в БД, будем вычислять на основе истории, но для простоты
        # считаем серию как количество дней подряд с активностью, начиная с today назад.
        # Простой способ: пока вернём 1, но можно посчитать из логов, если есть.
        # Пока оставим заглушку — позже можно добавить отдельную таблицу streak_log.
        # Для демонстрации вернём 1 (или можно хранить в users поле streak)
        # В вашей схеме нет поля streak, поэтому будем вычислять приблизительно.
        # Для упрощения: если активность сегодня, возвращаем 1 (можно позже улучшить).
        return 1
    elif delta == 1:
        # вчера была активность — серия увеличивается (но мы не знаем предыдущую)
        # если мы не храним серию, можно посчитать по логам, но для начала вернём 1
        return 1
    else:
        # больше дня назад — серия прервана, но если активность сегодня — начинаем новую
        return 1

# ---------- Сбор статистики по режимам ----------

async def get_progress_stats(user_id: int, type_key: str) -> dict:
    """
    Суммирует correct и wrong из таблицы progress для данного type_key (grammar, listening, reading, lexis)
    по всем уровням.
    """
    conn = await get_connection()
    rows = await conn.fetch(
        "SELECT SUM(correct) as total_correct, SUM(wrong) as total_wrong FROM progress WHERE user_id = $1 AND type_key = $2",
        user_id, type_key
    )
    await conn.close()
    row = rows[0] if rows else None
    correct = row["total_correct"] if row and row["total_correct"] else 0
    wrong = row["total_wrong"] if row and row["total_wrong"] else 0
    total = correct + wrong
    percent = round((correct / total * 100)) if total else 0
    return {"correct": correct, "wrong": wrong, "total": total, "percent": percent}

async def get_writing_stats(user_id: int) -> dict:
    """
    Суммирует total_answered и total_score из writing_progress по всем типам/уровням
    Возвращает средний балл.
    """
    conn = await get_connection()
    rows = await conn.fetch(
        "SELECT SUM(total_answered) as total_answered, SUM(total_score) as total_score FROM writing_progress WHERE user_id = $1",
        user_id
    )
    await conn.close()
    row = rows[0] if rows else None
    answered = row["total_answered"] if row and row["total_answered"] else 0
    score_sum = row["total_score"] if row and row["total_score"] else 0
    avg = round(score_sum / answered, 1) if answered else 0.0
    return {"answered": answered, "score_sum": score_sum, "avg": avg}

async def get_speaking_stats(user_id: int) -> dict:
    """
    Аналогично для govorenie_progress
    """
    conn = await get_connection()
    rows = await conn.fetch(
        "SELECT SUM(total_answered) as total_answered, SUM(total_score) as total_score FROM govorenie_progress WHERE user_id = $1",
        user_id
    )
    await conn.close()
    row = rows[0] if rows else None
    answered = row["total_answered"] if row and row["total_answered"] else 0
    score_sum = row["total_score"] if row and row["total_score"] else 0
    avg = round(score_sum / answered, 1) if answered else 0.0
    return {"answered": answered, "score_sum": score_sum, "avg": avg}

async def count_user_errors(user_id: int) -> dict:
    """Возвращает общее количество ошибок и разбивку по type_key"""
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

# ---------- Сброс прогресса ----------

async def reset_user_progress(user_id: int):
    """
    Сбрасывает весь прогресс пользователя во всех режимах, кроме:
    - общения с AI (нет данных)
    - ролевых игр (нет данных)
    Удаляет из таблиц: progress, errors, grammar_progress, writing_progress, govorenie_progress.
    """
    conn = await get_connection()
    await conn.execute("DELETE FROM progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM errors WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM grammar_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM writing_progress WHERE user_id = $1", user_id)
    await conn.execute("DELETE FROM govorenie_progress WHERE user_id = $1", user_id)
    # Не трогаем таблицу users (подписка, last_active и т.д.)
    await conn.close()

# ---------- Клавиатуры ----------

def get_profile_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🔧 Работа над ошибками", callback_data="profile_fix_mistakes")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="profile_settings")],
        [InlineKeyboardButton(text="💳 Подписка", callback_data="profile_subscription")],
        [InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="profile_reset_confirm")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_keyboard(notif_on: bool, time_str: str):
    notif_text = "Вкл" if notif_on else "Выкл"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔔 Уведомления: {notif_text}", callback_data="profile_notif_toggle"),
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

# ---------- Обработчики ----------

@router.callback_query(lambda c: c.data == "profile_menu")
async def profile_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    # Обновим время активности (для серии)
    await update_last_active(user_id)

    # Получаем профиль пользователя (подписка)
    profile = await get_user_profile(user_id)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    # Серия (упрощённо)
    streak = await calculate_streak(user_id)

    # Уровень – заглушка (можно позже добавить определение по количеству слов/тем)
    level = "A2"
    next_level = "B1"
    progress_to_next = 75  # пример

    # Сбор статистики по режимам
    # Грамматика, Аудирование, Чтение, Лексика
    skills = {}
    for mode in ["grammar", "listening", "reading", "lexis"]:
        data = await get_progress_stats(user_id, mode)
        if data["total"] > 0:
            skills[mode] = {"percent": data["percent"], "correct": data["correct"], "total": data["total"]}

    # Письмо
    writing = await get_writing_stats(user_id)
    if writing["answered"] > 0:
        skills["writing"] = {"avg": writing["avg"], "checks": writing["answered"]}

    # Говорение
    speaking = await get_speaking_stats(user_id)
    if speaking["answered"] > 0:
        skills["speaking"] = {"avg": speaking["avg"], "checks": speaking["answered"]}

    # Активность (AI и ролевые игры – данных нет, пока заглушки)
    # Можно добавить позже отдельные таблицы
    ai_messages = 0
    role_completed = 0
    role_started = 0

    # Ошибки
    mistakes = await count_user_errors(user_id)
    total_mistakes = mistakes["total"]
    by_mode = mistakes["by_mode"]

    # Определяем слабое место (навык с наименьшим процентом)
    weak_skill = None
    weak_percent = 100
    for mode, data in skills.items():
        if "percent" in data:
            if data["percent"] < weak_percent:
                weak_percent = data["percent"]
                weak_skill = mode
    if weak_skill is None:
        # если нет данных по процентам, смотрим средний балл письма/говорения
        for mode in ["writing", "speaking"]:
            if mode in skills and skills[mode].get("avg", 0) < 3.0:
                weak_skill = mode
                break

    # Формируем текст
    text = f"🔥 Серия: {streak} дней\n"
    text += f"📊 Ваш уровень: {level} — прогресс {progress_to_next}% до {next_level}\n\n"

    text += "📈 Навыки (общий прогресс):\n"
    # Тренажеры (проценты)
    for mode, data in skills.items():
        if "percent" in data:
            percent = data["percent"]
            bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
            emoji = "✅" if percent >= 80 else "⚠️" if percent < 50 else "📖"
            label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика"}.get(mode, mode.capitalize())
            text += f"{label}: {bar} {percent}% {emoji}\n"
    # Продуктивные (средний балл)
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

    text += "\n📚 Выучено слов: пока нет данных"  # можно добавить из лексики

    if total_mistakes > 0:
        text += f"\n\n⚠️ ВАЖНО: У вас {total_mistakes} ошибок ждут исправления!\n"
        if by_mode:
            parts = []
            for m, cnt in by_mode.items():
                label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика", "writing": "Письмо", "speaking": "Говорение"}.get(m, m.capitalize())
                parts.append(f"{label}: {cnt}")
            text += "   (" + ", ".join(parts) + ")\n"
    else:
        text += "\n✅ Ошибок для исправления нет! Отлично!\n"

    # Совет
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

    keyboard = get_profile_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_fix_mistakes")
async def profile_fix_mistakes(callback: CallbackQuery):
    user_id = callback.from_user.id
    mistakes = await count_user_errors(user_id)
    if mistakes["total"] == 0:
        await callback.answer("У вас нет ошибок для исправления!", show_alert=True)
        return
    # Показываем список режимов с ошибками
    text = "🔧 <b>Работа над ошибками</b>\n\nВыберите режим, в котором хотите исправить ошибки:\n"
    buttons = []
    for mode, cnt in mistakes["by_mode"].items():
        label = {"grammar": "Грамматика", "listening": "Аудирование", "reading": "Чтение", "lexis": "Лексика", "writing": "Письмо", "speaking": "Говорение"}.get(mode, mode.capitalize())
        buttons.append([InlineKeyboardButton(text=f"{label} ({cnt})", callback_data=f"fix_{mode}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# Заглушки для перехода в режим исправления (позже реализовать)
@router.callback_query(lambda c: c.data.startswith("fix_"))
async def fix_mode_callback(callback: CallbackQuery):
    mode = callback.data.split("_")[1]
    await callback.answer(f"Переход в режим исправления ошибок для {mode} (в разработке)", show_alert=True)
    # В реальности здесь должен быть вызов соответствующего хендлера с флагом ошибок

@router.callback_query(lambda c: c.data == "profile_settings")
async def profile_settings(callback: CallbackQuery):
    # Настройки пока храним в БД? В текущей схеме нет таблицы настроек.
    # Для демонстрации используем словарь в памяти (или добавим позже).
    # Пока просто покажем заглушку.
    keyboard = get_settings_keyboard(True, "10:00")
    await callback.message.edit_text("⚙️ <b>Настройки</b>\n\nУправляйте уведомлениями и временем.", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_notif_toggle")
async def profile_notif_toggle(callback: CallbackQuery):
    # Заглушка
    await callback.answer("Функция уведомлений будет доступна позже.", show_alert=True)
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_notif_time")
async def profile_notif_time(callback: CallbackQuery):
    # Заглушка
    await callback.answer("Настройка времени уведомлений будет доступна позже.", show_alert=True)
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_subscription")
async def profile_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    profile = await get_user_profile(user_id)
    sub_end = profile.get("subscription_end", 0) if profile else 0
    if sub_end and sub_end > int(datetime.now().timestamp()):
        expires = datetime.fromtimestamp(sub_end).strftime("%d.%m.%Y")
        text = f"💳 <b>Подписка активна</b>\n\nДата окончания: {expires}\n\nЧтобы продлить, нажмите кнопку ниже."
    else:
        text = "💳 <b>Подписка не активна</b>\n\nОформите подписку, чтобы получить полный доступ к тренажёру."
    await callback.message.edit_text(text, reply_markup=get_subscription_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_extend")
async def profile_extend(callback: CallbackQuery):
    await callback.message.answer("💳 Функция продления подписки будет доступна позже.\nСвяжитесь с поддержкой для оплаты.")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_reset_confirm")
async def profile_reset_confirm(callback: CallbackQuery):
    text = (
        "⚠️ <b>Внимание!</b>\n\n"
        "Вы действительно хотите сбросить весь прогресс?\n"
        "Будут удалены все данные по грамматике, аудированию, чтению, лексике, письму и говорению.\n"
        "Прогресс в общении с AI и ролевых играх не сбрасывается (там нет сохранённых данных).\n\n"
        "Это действие нельзя отменить.\n\n"
        "Введите слово <b>СБРОС</b> в поле для сообщения, чтобы подтвердить."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="profile_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    # Сохраняем флаг, что ожидается подтверждение (можно использовать FSM, но пока в памяти)
    # Для простоты используем временный словарь (не для продакшена)
    # В реальном боте лучше использовать FSM.
    # Здесь оставим заглушку – подтверждение через ввод текста будет обработано ниже.
    await callback.answer()

@router.message(F.text)
async def profile_reset_handle(message: Message):
    # Проверяем, ожидается ли подтверждение сброса (используем простой флаг в памяти)
    # Поскольку мы не используем FSM, для демонстрации проверим, что сообщение пришло после нажатия кнопки сброса.
    # В реальном проекте используйте FSM.
    # Для упрощения: если текст == "СБРОС", сбрасываем.
    if message.text.strip().upper() == "СБРОС":
        user_id = message.from_user.id
        await reset_user_progress(user_id)
        await message.answer("✅ Прогресс успешно сброшен. Вы начинаете с чистого листа.")
        # Возвращаем главное меню
        from handlers.start import show_main_menu
        await show_main_menu(message, edit=False)
    else:
        # Игнорируем другие сообщения (или можно ответить, что нужно ввести СБРОС)
        pass

@router.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: CallbackQuery):
    # Возвращаемся в главное меню
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()