from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import get_user_state, set_user_state

router = Router()

# Уровни
LEVELS_ROW1 = [("A1 (Beginner)", "A1"), ("A2 (Elementary)", "A2")]
LEVELS_ROW2 = [("B1 (Intermediate)", "B1"), ("B2 (Upper Intermediate)", "B2")]
LEVELS_SINGLE = [("C1 (Advanced)", "C1")]

# Список тематических уроков (без эмодзи)
THEMATIC_TOPICS = [
    "Present Simple vs Continuous",
    "Past Simple vs Present Perfect",
    "Модальные глаголы (can/could/must)",
    "Conditionals (0,1,2 типа)",
    "Пассивный залог",
    "Предлоги времени и места",
    "Фразовые глаголы (основные)",
    "Артикли a/an/the",
    "Степени сравнения прилагательных",
    "Косвенная речь",
    "Герундий и инфинитив",
    "Сложные союзы (although/despite)",
    "Лексика: путешествия",
    "Лексика: деловая переписка",
    "Лексика: семья и друзья",
    "Идиомы (10 популярных)",
    "Неправильные глаголы (тренажёр)",
    "Числительные и даты",
    "Вопросительные предложения (tag questions)",
    "Условные предложения 3 типа (wish/if only)"
]

TOPICS_PER_PAGE = 5  # количество тем на одной странице

# Хранилище текущей страницы для каждого пользователя (можно сохранять в state, но для простоты используем словарь)
user_page = {}

@router.callback_query(lambda c: c.data == "start_lessons")
async def lessons_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if "lessons" not in user_state:
        user_state["lessons"] = {}
    set_user_state(user_id, user_state)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"level_{code}") for name, code in LEVELS_ROW1],
        [InlineKeyboardButton(text=name, callback_data=f"level_{code}") for name, code in LEVELS_ROW2],
        [InlineKeyboardButton(text=name, callback_data=f"level_{code}") for name, code in LEVELS_SINGLE],
        [InlineKeyboardButton(text="Тематические уроки", callback_data="thematic_menu")],
        [InlineKeyboardButton(text="Моё обучение", callback_data="my_learning")],
        [InlineKeyboardButton(text="Пройти тест (уровень)", callback_data="placement_test")],
        [InlineKeyboardButton(text="Назад в главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "📚 Режим уроков\n\n"
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
    level_code = callback.data.split("_")[1]
    all_levels = LEVELS_ROW1 + LEVELS_ROW2 + LEVELS_SINGLE
    level_name = next((name for name, code in all_levels if code == level_code), level_code)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад к выбору уровня", callback_data="start_lessons")],
        [InlineKeyboardButton(text="Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"📖 Уровень {level_name}\n\n"
        "🚧 Режим в разработке.\n"
        "Скоро здесь появится полная программа обучения: грамматика, лексика, чтение, письмо, говорение.\n"
        "Вы сможете отслеживать прогресс и получать задания ИИ.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Тематические уроки с пагинацией ----------
def get_thematic_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Формирует клавиатуру для страницы тематических уроков"""
    start_idx = (page - 1) * TOPICS_PER_PAGE
    end_idx = start_idx + TOPICS_PER_PAGE
    page_topics = THEMATIC_TOPICS[start_idx:end_idx]

    buttons = []
    for idx, topic in enumerate(page_topics, start=start_idx):
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"thematic_{idx}")])

    # Панель навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀", callback_data="thematic_prev"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="thematic_none"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶", callback_data="thematic_next"))
    buttons.append(nav_buttons)

    # Кнопка возврата
    buttons.append([InlineKeyboardButton(text="К выбору тем", callback_data="start_lessons")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(lambda c: c.data == "thematic_menu")
async def thematic_lessons_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + TOPICS_PER_PAGE - 1) // TOPICS_PER_PAGE
    user_page[user_id] = 1  # сброс на первую страницу
    keyboard = get_thematic_keyboard(1, total_pages)
    await callback.message.edit_text(
        "Тематические уроки\n\nВыберите тему для изучения:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "thematic_next")
async def thematic_next_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + TOPICS_PER_PAGE - 1) // TOPICS_PER_PAGE
    current = user_page.get(user_id, 1)
    if current < total_pages:
        user_page[user_id] = current + 1
        keyboard = get_thematic_keyboard(current + 1, total_pages)
        await callback.message.edit_text(
            "Тематические уроки\n\nВыберите тему для изучения:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "thematic_prev")
async def thematic_prev_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + TOPICS_PER_PAGE - 1) // TOPICS_PER_PAGE
    current = user_page.get(user_id, 1)
    if current > 1:
        user_page[user_id] = current - 1
        keyboard = get_thematic_keyboard(current - 1, total_pages)
        await callback.message.edit_text(
            "Тематические уроки\n\nВыберите тему для изучения:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("thematic_") and c.data not in ("thematic_menu", "thematic_next", "thematic_prev", "thematic_none"))
async def thematic_topic_chosen(callback: CallbackQuery):
    idx_str = callback.data.split("_")[1]
    try:
        idx = int(idx_str)
        if 0 <= idx < len(THEMATIC_TOPICS):
            topic = THEMATIC_TOPICS[idx]
        else:
            await callback.answer("Тема не найдена", show_alert=True)
            return
    except ValueError:
        await callback.answer("Ошибка выбора темы", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать практику", callback_data=f"practice_thematic_{idx}")],
        [InlineKeyboardButton(text="Назад к темам", callback_data="thematic_menu")],
        [InlineKeyboardButton(text="Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"📖 {topic}\n\n"
        "🚧 Урок в разработке.\n"
        "Скоро здесь будет краткая теория и интерактивное задание.\n\n"
        "Пока вы можете вернуться назад.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Моё обучение ----------
@router.callback_query(lambda c: c.data == "my_learning")
async def my_learning_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lessons_data = user_state.get("lessons", {})
    level = lessons_data.get("level", "не выбран")
    completed_topics = lessons_data.get("completed_topics", [])
    total_correct = lessons_data.get("total_correct", 0)
    total_wrong = lessons_data.get("total_wrong", 0)

    progress_text = (
        f"📊 Ваш прогресс\n\n"
        f"🎯 Уровень: {level}\n"
        f"✅ Выполнено тем: {len(completed_topics)}\n"
        f"📈 Правильных ответов: {total_correct}\n"
        f"❌ Ошибок: {total_wrong}\n"
    )
    if total_correct + total_wrong > 0:
        percent = round(total_correct / (total_correct + total_wrong) * 100)
        progress_text += f"📊 Точность: {percent}%\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продолжить обучение", callback_data="continue_learning")],
        [InlineKeyboardButton(text="План недели", callback_data="weekly_plan")],
        [InlineKeyboardButton(text="Сменить уровень", callback_data="start_lessons")],
        [InlineKeyboardButton(text="Назад", callback_data="start_lessons")]
    ])
    await callback.message.edit_text(
        progress_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "continue_learning")
async def continue_learning(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lessons_data = user_state.get("lessons", {})
    current_topic = lessons_data.get("current_topic", "не начато")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад к прогрессу", callback_data="my_learning")],
        [InlineKeyboardButton(text="Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"🚧 Режим продолжения обучения в разработке.\n\n"
        f"Ваша последняя тема: {current_topic}\n"
        f"Как только система будет готова, вы сможете продолжить ровно с этого места.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "weekly_plan")
async def weekly_plan_menu(callback: CallbackQuery):
    default_plan = [
        "Пн: Present Simple (утверждение)",
        "Вт: Present Simple (отрицание и вопросы)",
        "Ср: Лексика: ежедневная рутина",
        "Чт: Past Simple (правильные глаголы)",
        "Пт: Past Simple (неправильные глаголы)",
        "Сб: Повторение недели + тест",
        "Вс: Выходной / свободная практика"
    ]
    plan_buttons = []
    for idx, day in enumerate(default_plan):
        plan_buttons.append([InlineKeyboardButton(text=day, callback_data=f"edit_plan_{idx}")])
    plan_buttons.append([InlineKeyboardButton(text="Добавить тему", callback_data="add_plan_item")])
    plan_buttons.append([InlineKeyboardButton(text="Назад", callback_data="my_learning")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=plan_buttons)
    await callback.message.edit_text(
        "План недели\n\n"
        "Ниже показаны темы для изучения. Вы можете:\n"
        "• Нажать на тему, чтобы изменить её\n"
        "• Добавить новую тему\n"
        "• Позже – удалять лишнее\n\n"
        "После утверждения плана бот будет ежедневно напоминать и присылать задания.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("edit_plan_"))
async def edit_plan_item(callback: CallbackQuery):
    await callback.answer("Редактирование плана в разработке", show_alert=True)

@router.callback_query(lambda c: c.data == "add_plan_item")
async def add_plan_item(callback: CallbackQuery):
    await callback.answer("Добавление темы в план в разработке", show_alert=True)

# ---------- Тест ----------
@router.callback_query(lambda c: c.data == "placement_test")
async def placement_test(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="start_lessons")],
        [InlineKeyboardButton(text="Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "Тест на определение уровня\n\n"
        "🚧 В разработке.\n"
        "Скоро здесь будет 15 вопросов, которые определят ваш точный уровень (от A1 до C1).",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- Назад в главное меню ----------
@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()