# handlers/profile.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from data.users import get_user_state, set_user_state

router = Router()

# ---------- Вспомогательные функции для работы с профилем ----------

def get_stats(user_id: int) -> dict:
    """Возвращает статистику пользователя с заполнением по умолчанию"""
    state = get_user_state(user_id)
    if "profile" not in state:
        state["profile"] = {
            "stats": {
                "lessons_completed": 0,
                "practices_completed": 0,
                "correct_answers": 0,
                "wrong_answers": 0,
                "streak": 0,
                "last_activity": None
            },
            "subscription": {
                "active": False,
                "expires": None
            },
            "settings": {
                "notifications": True,
                "notification_time": "10:00"
            }
        }
        set_user_state(user_id, state)
    return state["profile"]["stats"]

def update_streak(user_id: int):
    """Обновляет дни подряд (streak)"""
    state = get_user_state(user_id)
    profile = state.get("profile", {})
    stats = profile.get("stats", {})
    today = datetime.now().date()
    today_str = today.isoformat()
    last = stats.get("last_activity")
    
    if not last:
        stats["streak"] = 1
        stats["last_activity"] = today_str
    else:
        last_date = datetime.strptime(last, "%Y-%m-%d").date()
        delta = (today - last_date).days
        if delta == 0:
            # Уже обновлено сегодня — ничего не делаем
            pass
        elif delta == 1:
            stats["streak"] = stats.get("streak", 0) + 1
            stats["last_activity"] = today_str
        else:
            stats["streak"] = 1
            stats["last_activity"] = today_str
    state["profile"]["stats"] = stats
    set_user_state(user_id, state)

def update_stats_after_lesson(user_id: int):
    """Вызывается после завершения урока"""
    state = get_user_state(user_id)
    stats = state.get("profile", {}).get("stats", {})
    stats["lessons_completed"] = stats.get("lessons_completed", 0) + 1
    state["profile"]["stats"] = stats
    set_user_state(user_id, state)
    update_streak(user_id)

def update_stats_after_practice(user_id: int, correct: int, wrong: int):
    """Вызывается после завершения практики"""
    state = get_user_state(user_id)
    stats = state.get("profile", {}).get("stats", {})
    stats["practices_completed"] = stats.get("practices_completed", 0) + 1
    stats["correct_answers"] = stats.get("correct_answers", 0) + correct
    stats["wrong_answers"] = stats.get("wrong_answers", 0) + wrong
    state["profile"]["stats"] = stats
    set_user_state(user_id, state)
    update_streak(user_id)

def reset_profile(user_id: int) -> bool:
    """Сбрасывает прогресс (с защитой от случайного удаления)"""
    # Удаляем только profile, оставляя остальные данные (mode, history, etc.)
    state = get_user_state(user_id)
    if "profile" in state:
        del state["profile"]
        set_user_state(user_id, state)
        return True
    return False

# ---------- Клавиатуры ----------

def get_profile_keyboard():
    """Главное меню профиля"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="profile_stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="profile_settings")],
        [InlineKeyboardButton(text="💳 Подписка", callback_data="profile_subscription")],
        [InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="profile_reset_confirm")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_settings_keyboard():
    """Клавиатура настроек"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Уведомления: Вкл", callback_data="profile_notif_toggle"),
         InlineKeyboardButton(text="⏰ Время: 10:00", callback_data="profile_notif_time")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")]
    ])

def get_subscription_keyboard():
    """Клавиатура подписки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="profile_extend")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")]
    ])

def get_confirm_reset_keyboard():
    """Подтверждение сброса прогресса"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="profile_reset_do")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="profile_back")]
    ])

# ---------- Обработчики ----------

@router.callback_query(lambda c: c.data == "profile_menu")
async def profile_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    update_streak(user_id)  # обновляем streak при входе в профиль
    stats = get_stats(user_id)
    profile = get_user_state(user_id).get("profile", {})
    sub = profile.get("subscription", {})
    
    text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"📘 <b>Прогресс:</b>\n"
        f"   Уроков пройдено: {stats.get('lessons_completed', 0)}\n"
        f"   Практик пройдено: {stats.get('practices_completed', 0)}\n"
        f"   ✅ Правильных ответов: {stats.get('correct_answers', 0)}\n"
        f"   ❌ Неправильных: {stats.get('wrong_answers', 0)}\n"
    )
    total = stats.get('correct_answers', 0) + stats.get('wrong_answers', 0)
    if total:
        percent = int(stats.get('correct_answers', 0) / total * 100)
        text += f"   📊 Точность: {percent}%\n"
    else:
        text += f"   📊 Точность: —\n"
    text += f"   🔥 Дней подряд: {stats.get('streak', 0)}\n\n"
    
    if sub.get("active"):
        expires = sub.get("expires")
        if expires:
            text += f"💳 <b>Подписка активна</b> до {expires}\n"
        else:
            text += f"💳 <b>Подписка активна</b>\n"
    else:
        text += f"💳 <b>Подписка не активна</b>\n"
    
    await callback.message.edit_text(text, reply_markup=get_profile_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_stats")
async def profile_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    stats = get_stats(user_id)
    text = (
        f"📊 <b>Детальная статистика</b>\n\n"
        f"📘 Уроков пройдено: {stats.get('lessons_completed', 0)}\n"
        f"📝 Практик пройдено: {stats.get('practices_completed', 0)}\n"
        f"✅ Правильных ответов: {stats.get('correct_answers', 0)}\n"
        f"❌ Неправильных: {stats.get('wrong_answers', 0)}\n"
    )
    total = stats.get('correct_answers', 0) + stats.get('wrong_answers', 0)
    if total:
        percent = int(stats.get('correct_answers', 0) / total * 100)
        text += f"📊 Точность: {percent}%\n"
    else:
        text += f"📊 Точность: —\n"
    text += f"🔥 Дней подряд: {stats.get('streak', 0)}\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")]
    ]), parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_settings")
async def profile_settings(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    settings = state.get("profile", {}).get("settings", {})
    notif = settings.get("notifications", True)
    notif_text = "Вкл" if notif else "Выкл"
    time = settings.get("notification_time", "10:00")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔔 Уведомления: {notif_text}", callback_data="profile_notif_toggle"),
         InlineKeyboardButton(text=f"⏰ Время: {time}", callback_data="profile_notif_time")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")]
    ])
    await callback.message.edit_text("⚙️ <b>Настройки</b>\n\nУправляйте уведомлениями и временем.", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_notif_toggle")
async def profile_notif_toggle(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    settings = state.get("profile", {}).get("settings", {})
    settings["notifications"] = not settings.get("notifications", True)
    state["profile"]["settings"] = settings
    set_user_state(user_id, state)
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_notif_time")
async def profile_notif_time(callback: CallbackQuery):
    # Простое изменение времени с шагом 1 час
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    settings = state.get("profile", {}).get("settings", {})
    current = settings.get("notification_time", "10:00")
    hour = int(current.split(":")[0])
    new_hour = (hour + 1) % 24
    new_time = f"{new_hour:02d}:00"
    settings["notification_time"] = new_time
    state["profile"]["settings"] = settings
    set_user_state(user_id, state)
    await profile_settings(callback)

@router.callback_query(lambda c: c.data == "profile_subscription")
async def profile_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    sub = state.get("profile", {}).get("subscription", {})
    if sub.get("active"):
        expires = sub.get("expires", "не указана")
        text = f"💳 <b>Подписка активна</b>\n\nДата окончания: {expires}\n\nЧтобы продлить, нажмите кнопку ниже."
    else:
        text = "💳 <b>Подписка не активна</b>\n\nОформите подписку, чтобы получить полный доступ к тренажёру."
    await callback.message.edit_text(text, reply_markup=get_subscription_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_extend")
async def profile_extend(callback: CallbackQuery):
    # Заглушка для оплаты
    await callback.message.answer("💳 Функция продления подписки будет доступна позже.\nСвяжитесь с поддержкой для оплаты.")
    await callback.answer()

@router.callback_query(lambda c: c.data == "profile_reset_confirm")
async def profile_reset_confirm(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚠️ <b>Внимание!</b>\n\nВы действительно хотите сбросить весь прогресс?\n"
        "Это действие нельзя отменить.\n\n"
        "Введите слово <b>СБРОС</b> в поле для сообщения, чтобы подтвердить.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="profile_back")]
        ]),
        parse_mode="HTML"
    )
    # Устанавливаем флаг ожидания подтверждения
    state = get_user_state(callback.from_user.id)
    state["profile_reset_pending"] = True
    set_user_state(callback.from_user.id, state)
    await callback.answer()

# Обработчик текстового подтверждения сброса
@router.message(F.text)
async def profile_reset_handle(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    if state.get("profile_reset_pending"):
        if message.text.strip().upper() == "СБРОС":
            if reset_profile(user_id):
                await message.answer("✅ Прогресс успешно сброшен. Вы начинаете с чистого листа.")
            else:
                await message.answer("ℹ️ Прогресс не был найден.")
            state["profile_reset_pending"] = False
            set_user_state(user_id, state)
            # Вернуть в главное меню
            from handlers.start import show_main_menu
            await show_main_menu(message, edit=False)
        else:
            await message.answer("❌ Неверное слово. Попробуйте ещё раз или нажмите «Отмена».")
            # Не сбрасываем флаг, даём ещё попытку

@router.callback_query(lambda c: c.data == "profile_back")
async def profile_back(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    # Снимаем флаг ожидания сброса, если он был
    state["profile_reset_pending"] = False
    set_user_state(user_id, state)
    await profile_menu(callback)