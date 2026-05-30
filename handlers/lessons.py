from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import get_user_state, set_user_state

router = Router()

# Список уровней с группами для компактного отображения
LEVELS_ROW1 = [("A1 (Beginner)", "A1"), ("A2 (Elementary)", "A2")]
LEVELS_ROW2 = [("B1 (Intermediate)", "B1"), ("B2 (Upper Intermediate)", "B2")]
LEVELS_SINGLE = [("C1 (Advanced)", "C1")]

# Список тематических уроков (20+ тем для старта, позже добавим практику)
THEMATIC_TOPICS = [
    "📖 Present Simple vs Continuous",
    "📖 Past Simple vs Present Perfect",
    "📖 Модальные глаголы (can/could/must)",
    "📖 Conditionals (0,1,2 типа)",
    "📖 Пассивный залог",
    "📖 Предлоги времени и места",
    "📖 Фразовые глаголы (основные)",
    "📖 Артикли a/an/the",
    "📖 Степени сравнения прилагательных",
    "📖 Косвенная речь",
    "📖 Герундий и инфинитив",
    "📖 Сложные союзы (although/despite)",
    "📖 Лексика: путешествия",
    "📖 Лексика: деловая переписка",
    "📖 Лексика: семья и друзья",
    "📖 Идиомы (10 популярных)",
    "📖 Неправильные глаголы (тренажёр)",
    "📖 Числительные и даты",
    "📖 Вопросительные предложения (tag questions)",
    "📖 Условные предложения 3 типа (wish/if only)"
]

@router.callback_query(lambda c: c.data == "start_lessons")
async def lessons_menu(callback: CallbackQuery):
    """Главное меню уроков: выбор уровня, тематические уроки, моё обучение, тест"""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if "lessons" not in user_state:
        user_state["lessons"] = {}
    set_user_state(user_id, user_state)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        # Уровни в две строки: A1/A2 вместе, B1/B2 вместе, C1 отдельно
        [InlineKeyboardButton(text=name, callback_data=f"level_{code}") for name, code in LEVELS_ROW1],
        [InlineKeyboardButton(text=name, callback_data=f"level_{code}") for name, code in LEVELS_ROW2],
        [InlineKeyboardButton(text=name, callback_data=f"level_{code}") for name, code in LEVELS_SINGLE],
        # Дополнительные кнопки
        [InlineKeyboardButton(text="📚 Тематические уроки", callback_data="thematic_menu")],
        [InlineKeyboardButton(text="📊 Моё обучение", callback_data="my_learning")],
        [InlineKeyboardButton(text="📝 Пройти тест (уровень)", callback_data="placement_test")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "📚 <b>Режим уроков</b>\n\n"
        "Выберите свой уровень, чтобы начать системное обучение.\n"
        "Или откройте «Тематические уроки» для быстрого разбора конкретных тем.\n"
        "«Моё обучение» — ваш прогресс и план на неделю.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Уровни ----------
@router.callback_query(lambda c: c.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery):
    """Выбор уровня – заглушка (позже здесь будет запуск программы уровня)"""
    level_code = callback.data.split("_")[1]
    # Найдём название уровня
    all_levels = LEVELS_ROW1 + LEVELS_ROW2 + LEVELS_SINGLE
    level_name = next((name for name, code in all_levels if code == level_code), level_code)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к выбору уровня", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"📖 <b>Уровень {level_name}</b>\n\n"
        "🚧 Режим в разработке.\n"
        "Скоро здесь появится полная программа обучения: грамматика, лексика, чтение, письмо, говорение.\n"
        "Вы сможете отслеживать прогресс и получать задания ИИ.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Тематические уроки ----------
@router.callback_query(lambda c: c.data == "thematic_menu")
async def thematic_lessons_menu(callback: CallbackQuery):
    """Список тематических уроков (без уровней)"""
    buttons = []
    for topic in THEMATIC_TOPICS[:12]:  # первые 12 в одной странице, остальные можно постранично или скроллом
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"thematic_{topic[:30]}")])
    # Добавим кнопку "Загрузить ещё" для остальных
    if len(THEMATIC_TOPICS) > 12:
        buttons.append([InlineKeyboardButton(text="📂 Показать ещё", callback_data="thematic_more")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "📚 <b>Тематические уроки</b>\n\n"
        "Выберите тему для самостоятельного изучения.\n"
        "Каждый урок включает короткую теорию и практическое задание с проверкой ИИ.\n"
        "Прогресс по тематическим урокам не сохраняется (можно проходить в любом порядке).",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("thematic_"))
async def thematic_topic_chosen(callback: CallbackQuery):
    """Выбор конкретной темы – заглушка (позже генерация задания)"""
    topic = callback.data.split("_", 1)[1]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Начать практику", callback_data=f"practice_thematic_{topic}")],
        [InlineKeyboardButton(text="🔙 Назад к темам", callback_data="thematic_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"📖 <b>{topic}</b>\n\n"
        "🚧 Урок в разработке.\n"
        "Скоро здесь будет краткая теория и интерактивное задание.\n\n"
        "Пока вы можете вернуться назад.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "thematic_more")
async def thematic_more(callback: CallbackQuery):
    """Показать оставшиеся темы"""
    # В реальности нужно хранить страницу, для простоты покажем вторую страницу
    remaining = THEMATIC_TOPICS[12:]
    buttons = []
    for topic in remaining:
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"thematic_{topic[:30]}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="thematic_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "📚 <b>Тематические уроки (продолжение)</b>\n\n"
        "Выберите тему:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Моё обучение (прогресс + план недели) ----------
@router.callback_query(lambda c: c.data == "my_learning")
async def my_learning_menu(callback: CallbackQuery):
    """Показывает прогресс пользователя и предлагает план недели"""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lessons_data = user_state.get("lessons", {})
    level = lessons_data.get("level", "не выбран")
    completed_topics = lessons_data.get("completed_topics", [])
    total_correct = lessons_data.get("total_correct", 0)
    total_wrong = lessons_data.get("total_wrong", 0)

    progress_text = (
        f"📊 <b>Ваш прогресс</b>\n\n"
        f"🎯 Уровень: <b>{level}</b>\n"
        f"✅ Выполнено тем: {len(completed_topics)}\n"
        f"📈 Правильных ответов: {total_correct}\n"
        f"❌ Ошибок: {total_wrong}\n"
    )
    if total_correct + total_wrong > 0:
        percent = round(total_correct / (total_correct + total_wrong) * 100)
        progress_text += f"📊 Точность: {percent}%\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Продолжить обучение", callback_data="continue_learning")],
        [InlineKeyboardButton(text="📅 План недели", callback_data="weekly_plan")],
        [InlineKeyboardButton(text="🔄 Сменить уровень", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")]
    ])
    await callback.message.edit_text(
        progress_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "continue_learning")
async def continue_learning(callback: CallbackQuery):
    """Заглушка – продолжит урок с последней темы"""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lessons_data = user_state.get("lessons", {})
    current_topic = lessons_data.get("current_topic", "не начато")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к прогрессу", callback_data="my_learning")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"🚧 Режим продолжения обучения в разработке.\n\n"
        f"Ваша последняя тема: <b>{current_topic}</b>\n"
        f"Как только система будет готова, вы сможете продолжить ровно с этого места.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "weekly_plan")
async def weekly_plan_menu(callback: CallbackQuery):
    """План недели – пользователь может редактировать"""
    # Пример плана по умолчанию (для A1/A2)
    default_plan = [
        "Пн: Present Simple (утверждение)",
        "Вт: Present Simple (отрицание и вопросы)",
        "Ср: Лексика: ежедневная рутина",
        "Чт: Past Simple (правильные глаголы)",
        "Пт: Past Simple (неправильные глаголы)",
        "Сб: Повторение недели + тест",
        "Вс: Выходной / свободная практика"
    ]
    # Для каждого дня сделаем кнопку "✏️ изменить" (пока заглушка)
    plan_buttons = []
    for day in default_plan:
        plan_buttons.append([InlineKeyboardButton(text=day, callback_data=f"edit_plan_{day[:10]}")])
    plan_buttons.append([InlineKeyboardButton(text="➕ Добавить тему", callback_data="add_plan_item")])
    plan_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="my_learning")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=plan_buttons)
    await callback.message.edit_text(
        "📅 <b>Ваш план недели</b>\n\n"
        "Ниже показаны темы для изучения. Вы можете:\n"
        "• Нажать на тему, чтобы изменить её\n"
        "• Добавить новую тему\n"
        "• Позже – удалять лишнее\n\n"
        "После утверждения плана бот будет ежедневно напоминать и присылать задания.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# Заглушки для редактирования плана (можно реализовать позже через FSM)
@router.callback_query(lambda c: c.data.startswith("edit_plan_"))
async def edit_plan_item(callback: CallbackQuery):
    await callback.answer("Редактирование плана в разработке", show_alert=True)

@router.callback_query(lambda c: c.data == "add_plan_item")
async def add_plan_item(callback: CallbackQuery):
    await callback.answer("Добавление темы в план в разработке", show_alert=True)

# ---------- Тест на определение уровня ----------
@router.callback_query(lambda c: c.data == "placement_test")
async def placement_test(callback: CallbackQuery):
    """Заглушка теста"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "📝 <b>Тест на определение уровня</b>\n\n"
        "🚧 В разработке.\n"
        "Скоро здесь будет 15 вопросов, которые определят ваш точный уровень (от A1 до C1).",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Назад в главное меню ----------
@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    from handlers.start import show_main_menu  # импортируем функцию, которую создадим ниже
    await show_main_menu(callback.message, edit=True)
    await callback.answer()