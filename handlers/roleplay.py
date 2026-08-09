import re
import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from data.users import get_user_state, set_user_state
from services.deepseek import chat
from speaking.services.stt import voice_to_text

logger = logging.getLogger(__name__)
router = Router()

class RoleplayStates(StatesGroup):
    active = State()
    confirming_exit = State()
    confirming_finish = State()

# ---------- КАТЕГОРИИ ----------
CATEGORIES = [
    ("💼 Work & Business", "work"),
    ("✈️ Travel", "travel"),
    ("🏠 Daily Life", "daily"),
    ("💪 Health & Fitness", "health"),
    ("👨‍👩‍👧 Family & Home", "family"),
    ("📱 Technology", "tech"),
    ("💅 Beauty Routine", "beauty"),
    ("🛍️ Shopping & Dining", "shopping"),
    ("🗣️ Small Talk", "small_talk"),
    ("🎓 Education", "education"),
    ("💰 Finance & Banking", "finance"),
    ("🚗 Cars & Transport", "cars"),
    ("🏡 Real Estate", "realestate"),
    ("🎬 Culture", "entertainment"),
    ("🌿 Nature & Outdoors", "nature"),
    ("🧠 Psychology", "psychology"),
    ("🆘 Emergency", "emergency"),
    ("🍳 Cooking & Recipes", "cooking"),
    ("💅🏽 Fashion & Style", "fashion"),
    ("📰 News", "news")
]

# ---------- ТЕМЫ (здесь вставьте свой полный словарь TOPICS) ----------
# ВАЖНО: замените этот словарь на ваш (я оставил пустые списки для краткости,
# но вы должны вставить полный TOPICS из вашего файла)
TOPICS = {
    "work": [],
    "travel": [],
    "daily": [],
    "health": [],
    "family": [],
    "tech": [],
    "beauty": [],
    "shopping": [],
    "small_talk": [],
    "education": [],
    "finance": [],
    "cars": [],
    "realestate": [],
    "entertainment": [],
    "nature": [],
    "psychology": [],
    "emergency": [],
    "cooking": [],
    "fashion": [],
    "news": []
}

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_categories_keyboard():
    buttons = []
    for i in range(0, len(CATEGORIES), 2):
        row = []
        cat1 = CATEGORIES[i]
        row.append(InlineKeyboardButton(text=cat1[0], callback_data=f"cat_{cat1[1]}"))
        if i+1 < len(CATEGORIES):
            cat2 = CATEGORIES[i+1]
            row.append(InlineKeyboardButton(text=cat2[0], callback_data=f"cat_{cat2[1]}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="back_to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def is_cyrillic(text: str) -> bool:
    return bool(re.search('[а-яА-Я]', text))

# ---------- ФИЛЬТР ЗАПРЕЩЁННЫХ ТЕМ ----------
FORBIDDEN_WORDS = [
    "fuck", "bitch", "shit", "cunt", "dick", "pussy", "fucking", "motherfucker", "asshole", "bastard", "damn",
    "penis", "vagina", "cum", "orgasm", "masturbate", "sperm", "erection", "prostitute", "porn", "xxx",
    "suicide", "kill myself", "cut myself", "self-harm", "die", "death", "hang myself", "overdose",
    "murder", "rape", "torture", "assault", "kill", "terrorist", "bomb", "shoot", "stab",
    "nazi", "hitler", "stalin", "terrorism", "dictator", "fascist", "communist", "putin", "zelensky", "trump", "biden",
    "allah", "muhammad", "jesus", "bible", "quran", "prophet", "church", "mosque", "synagogue", "god", "holy", "priest", "imam",
    "stupid", "idiot", "moron", "loser", "ugly", "fat", "worthless", "retard", "whore"
]

def is_forbidden(text: str) -> bool:
    lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in lower:
            return True
    return False

# ---------- СИСТЕМНЫЙ ПРОМПТ (ИИ ОТВЕЧАЕТ ТОЛЬКО НА АНГЛИЙСКОМ) ----------
def build_system_prompt(topic: str, description: str, goals: list) -> str:
    goals_text = "\n".join([f"{i+1}. {g}" for i, g in enumerate(goals)])
    return (
        f"You are a character in a role-playing game for learning English. "
        f"Situation: {description}\n"
        f"Topic: {topic}\n"
        f"User's goals: {goals_text}\n\n"
        "Your task is to lead the dialogue within this situation. You must help the user practice English, but stay in character.\n\n"
        "IMPORTANT RULES:\n"
        "1. You ALWAYS respond in ENGLISH only. Never switch to Russian, regardless of the user's language.\n"
        "2. Always bring the user back to the topic if they stray from it. Gently but firmly remind them of the situation.\n"
        "3. You do not discuss topics unrelated to the role-play. Do not answer questions about yourself, the real world, politics, religion, sex, violence, or suicide.\n"
        "4. If the user asks about something forbidden, respond with: 'Let's return to our situation' and continue the game.\n"
        "5. At the end of each of your responses, assess whether the user has achieved all goals. If all goals are achieved and the dialogue has more than 5 exchanges, add this phrase: 'It seems we've reached a logical conclusion to this situation. If you'd like, we can wrap up and get feedback. If you prefer to continue, just keep chatting.'\n"
        "6. Respond naturally, in character.\n"
    )

async def call_ai_with_system(system_prompt: str, user_text: str, history: list) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["text"]})
    messages.append({"role": "user", "content": user_text})
    prompt = ""
    for m in messages:
        prompt += f"{m['role']}: {m['content']}\n"
    try:
        response = await chat(prompt, max_tokens=500, temperature=0.7)
        return response
    except Exception as e:
        logger.error(f"Ошибка вызова ИИ: {e}")
        return "Произошла ошибка. Попробуйте ещё раз."

# ---------- СТАРТ РОЛЕВОЙ ИГРЫ ----------
@router.callback_query(F.data == "start_roleplay")
async def start_roleplay(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} entered roleplay")
    await callback.message.delete()
    await callback.message.answer(
        "🎭 Выберите категорию для ролевой игры:",
        reply_markup=get_categories_keyboard()
    )
    await callback.answer()

# ---------- ПОКАЗ ТЕМ С ПАГИНАЦИЕЙ ----------
@router.callback_query(F.data.startswith("cat_"))
async def show_topics(callback: CallbackQuery, cat_id: str = None, page: int = 0):
    if cat_id is None:
        cat_id = callback.data[4:]  # убираем "cat_"
    logger.info(f"Show topics for category {cat_id}, page {page}")
    topics_list = TOPICS.get(cat_id, [])
    if not topics_list:
        await callback.answer("В этой категории нет тем", show_alert=True)
        return

    ITEMS_PER_PAGE = 4
    total = len(topics_list)
    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    start = page * ITEMS_PER_PAGE
    end = min(start + ITEMS_PER_PAGE, total)
    page_topics = topics_list[start:end]

    buttons = []
    for idx, topic_info in enumerate(page_topics, start=start):
        buttons.append([InlineKeyboardButton(
            text=topic_info["name"],
            callback_data=f"topic_{cat_id}_{idx}_{page}"
        )])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"cat_page_{cat_id}_{page-1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"cat_page_{cat_id}_{page+1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="back_to_rp_categories")])

    topics_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    cat_display = next((c[0] for c in CATEGORIES if c[1] == cat_id), cat_id)
    await callback.message.edit_text(
        f"<b>{cat_display}</b>",
        reply_markup=topics_keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- ОБРАБОТЧИК СТРЕЛОК (ИСПРАВЛЕН) ----------
@router.callback_query(F.data.startswith("cat_page_"))
async def change_topic_page(callback: CallbackQuery):
    # Формат: cat_page_{cat_id}_{page}
    # Используем rsplit для отделения номера страницы
    rest = callback.data[9:]  # убираем "cat_page_"
    cat_id, page_str = rest.rsplit('_', 1)
    page = int(page_str)
    logger.info(f"Page change: category {cat_id}, page {page}")
    await show_topics(callback, cat_id=cat_id, page=page)

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer("")

# ---------- ВЫБОР ТЕМЫ (ИСПРАВЛЕН) ----------
@router.callback_query(F.data.startswith("topic_"))
async def topic_chosen(callback: CallbackQuery, state: FSMContext):
    # Формат: topic_{cat_id}_{idx}_{page}
    rest = callback.data[6:]  # убираем "topic_"
    # Разделяем на cat_id, idx, page с помощью rsplit
    parts = rest.rsplit('_', 2)
    if len(parts) != 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    cat_id = parts[0]
    idx = int(parts[1])
    page = int(parts[2])  # page не используется, но сохраняем для возврата

    topics_list = TOPICS.get(cat_id, [])
    if idx >= len(topics_list):
        await callback.answer("Тема не найдена", show_alert=True)
        return
    topic_info = topics_list[idx]
    topic = topic_info["name"]
    description = topic_info["description"]
    goals = topic_info["goals"]

    user_id = callback.from_user.id
    logger.info(f"User {user_id} selected topic '{topic}' from category {cat_id}")

    set_user_state(user_id, {
        "mode": "roleplay_active",
        "roleplay_history": [],
        "roleplay_topic": topic,
        "roleplay_description": description,
        "roleplay_goals": goals,
        "roleplay_category": cat_id,
        "roleplay_custom_scenario": None,
        "awaiting_custom_scenario": False,
        "russian_counter": 0
    })

    await state.set_state(RoleplayStates.active)
    await callback.answer(f"Выбрана тема: {topic}")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Завершить диалог")]
        ],
        resize_keyboard=True
    )
    goals_text = "\n".join([f"{i+1}) {goal}" for i, goal in enumerate(goals)])
    roleplay_info = (
        f"🎭 <b>Ролевая игра: {topic}</b>\n\n"
        f"📖 Ситуация: {description}\n\n"
        f"🎯 Ваши цели:\n{goals_text}\n\n"
        f"🗣️ <b>Говорите голосом или пишите текстом.</b>"
    )

    # Кнопка "Назад к темам"
    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к темам", callback_data=f"back_to_topics_{cat_id}_{page}")]
    ])

    await callback.message.edit_text(roleplay_info, parse_mode="HTML", reply_markup=back_button)
    await callback.message.answer("🎬 <b>Можете начинать!</b>", reply_markup=keyboard, parse_mode="HTML")

# ---------- НАЗАД К ТЕМАМ ----------
@router.callback_query(F.data.startswith("back_to_topics_"))
async def back_to_topics(callback: CallbackQuery):
    rest = callback.data[15:]  # убираем "back_to_topics_"
    cat_id, page_str = rest.rsplit('_', 1)
    page = int(page_str)
    await show_topics(callback, cat_id=cat_id, page=page)
    await callback.answer()

# ---------- НАЗАД К КАТЕГОРИЯМ ----------
@router.callback_query(F.data == "back_to_rp_categories")
async def back_to_rp_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🎭 Выберите категорию для ролевой игры:",
        reply_markup=get_categories_keyboard()
    )
    await callback.answer()

# ---------- ВОЗВРАТ В ГЛАВНОЕ МЕНЮ (БЕЗ ПОДТВЕРЖДЕНИЯ) ----------
@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    # Завершаем диалог
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    user_state["roleplay_history"] = []
    user_state["russian_counter"] = 0
    set_user_state(user_id, user_state)
    await callback.message.edit_text("Диалог завершен..🏁", reply_markup=None)
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False, remove_keyboard=True)
    await callback.answer()

# ---------- ОБРАБОТЧИК ВСЕХ КОМАНД (ДЛЯ ВЫХОДА) ----------
@router.message(F.text.startswith('/'))
async def handle_any_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") == "roleplay_active":
        # Если пользователь в игре – завершаем диалог
        user_state["mode"] = ""
        user_state["roleplay_history"] = []
        user_state["russian_counter"] = 0
        set_user_state(user_id, user_state)
        await state.clear()
        await message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
        # После завершения выполняем команду, если она известна
        # Для /start, /subscription, /support – обрабатываем отдельно
        command = message.text
        if command == "/start":
            from handlers.start import cmd_start
            await cmd_start(message, state)
        elif command == "/subscription":
            from handlers.subscription import cmd_subscription
            await cmd_subscription(message, state)
        elif command == "/support":
            from handlers.support import cmd_support
            await cmd_support(message, state)
        else:
            # Для всех остальных команд просто показываем главное меню
            from handlers.start import show_main_menu
            await show_main_menu(message, edit=False, remove_keyboard=True)
    else:
        # Если не в игре – просто передаём управление дальше
        # (можно не обрабатывать, но чтобы не блокировать другие команды)
        # Однако мы уже перехватили, нужно пропустить через стандартные хендлеры
        # Чтобы не ломать другие модули, передадим сообщение дальше
        # Для этого можно использовать диспетчер, но проще вызвать соответствующие функции
        command = message.text
        if command == "/start":
            from handlers.start import cmd_start
            await cmd_start(message, state)
        elif command == "/subscription":
            from handlers.subscription import cmd_subscription
            await cmd_subscription(message, state)
        elif command == "/support":
            from handlers.support import cmd_support
            await cmd_support(message, state)
        # else: ничего не делаем, пусть другие хендлеры обрабатывают

# ---------- ЗАВЕРШИТЬ ДИАЛОГ (КНОПКА) ----------
@router.message(RoleplayStates.active, F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("roleplay_history", [])
    goals = user_state.get("roleplay_goals", [])
    topic = user_state.get("roleplay_topic", "")

    if not history:
        await message.answer("Вы пока ничего не сказали. Начните разговор!", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    # Проверка достижения целей (упрощённо, чтобы не грузить)
    if goals:
        check_prompt = (
            "Analyze the dialogue and determine if the user has achieved all the goals. "
            "Answer only 'Yes' or 'No'.\n\n"
            "User's goals:\n" + chr(10).join(goals) + "\n\n"
            "Dialogue:\n" + chr(10).join([f'{m["role"]}: {m["text"]}' for m in history]) + "\n\n"
            "Has the user achieved all goals? Answer only 'Yes' or 'No'."
        )
        try:
            check_response = await chat(check_prompt, max_tokens=10, temperature=0)
            goals_achieved = "yes" in check_response.lower()
        except Exception as e:
            logger.error(f"Ошибка проверки целей: {e}")
            goals_achieved = False

        if not goals_achieved:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Продолжить диалог", callback_data="continue_dialogue"),
                 InlineKeyboardButton(text="Завершить всё равно", callback_data="finish_anyway")]
            ])
            await message.answer(
                "Вы ещё не достигли всех целей в этой ситуации. Хотите продолжить или завершить и получить фидбек?",
                reply_markup=keyboard
            )
            await state.set_state(RoleplayStates.confirming_finish)
            return

    await generate_feedback(message, state, user_id, user_state)

@router.callback_query(F.data == "continue_dialogue", RoleplayStates.confirming_finish)
async def continue_dialogue(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Продолжаем диалог. Достигните всех целей и завершите позже.", reply_markup=None)
    await callback.answer()

@router.callback_query(F.data == "finish_anyway", RoleplayStates.confirming_finish)
async def finish_anyway(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    await callback.message.delete()
    await generate_feedback(callback.message, state, user_id, user_state)
    await callback.answer()

# ---------- ГЕНЕРАЦИЯ ФИДБЕКА ----------
async def generate_feedback(message: Message, state: FSMContext, user_id: int, user_state: dict):
    history = user_state.get("roleplay_history", [])
    goals = user_state.get("roleplay_goals", [])
    topic = user_state.get("roleplay_topic", "")

    if not history:
        await message.answer("Нет диалога для анализа.", reply_markup=ReplyKeyboardRemove())
        return

    is_short = len(history) < 4

    theme_check_prompt = (
        "Analyze the dialogue. Determine if the user stayed on topic '" + topic + "'. "
        "Answer only 'Yes' or 'No'.\n\n"
        "Dialogue:\n" + chr(10).join([f'{m["role"]}: {m["text"]}' for m in history]) + "\n\n"
        "Did the user stay on topic? Answer only 'Yes' or 'No'."
    )
    try:
        theme_check = await chat(theme_check_prompt, max_tokens=10, temperature=0)
        off_topic = "no" in theme_check.lower()
    except Exception:
        off_topic = False

    dialog_text = chr(10).join([f'{m["role"]}: {m["text"]}' for m in history])
    goals_text = chr(10).join(goals) if goals else "Нет целей"

    feedback_prompt = (
        "Ты – языковой тренер. Проанализируй диалог пользователя с ИИ в ролевой игре и дай краткий фидбек на русском языке.\n"
        "Учти следующие моменты:\n"
        "- Если диалог был коротким (менее 4 сообщений), укажи это и предложи больше практиковаться.\n"
        "- Если пользователь отходил от темы, мягко укажи на это и напомни тему.\n"
        "- Выдели 2-3 основные грамматические ошибки с исправлениями.\n"
        "- Отметь удачные фразы и предложи, что можно улучшить.\n"
        "- Оцени, насколько пользователь достиг целей.\n"
        "Будь конструктивным, обращайся на 'ты'.\n\n"
        "Тема: " + topic + "\n"
        "Цели пользователя: " + goals_text + "\n"
        "Диалог:\n" + dialog_text + "\n\n"
        "Фидбек:"
    )

    if is_short:
        feedback_prompt += "\n\nДиалог был коротким. Упомяни это в фидбеке."
    if off_topic:
        feedback_prompt += "\n\nПользователь отклонялся от темы. Напомни, что нужно было обсуждать '" + topic + "'."

    try:
        feedback = await chat(feedback_prompt, max_tokens=500, temperature=0.5)
    except Exception as e:
        logger.error(f"Ошибка получения фидбека: {e}")
        await message.answer("Не удалось получить фидбек. Попробуйте позже.")
        return

    user_state["mode"] = ""
    user_state["roleplay_history"] = []
    user_state["russian_counter"] = 0
    set_user_state(user_id, user_state)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Начать новую игру", callback_data="start_roleplay")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main_menu")]
    ])
    await message.answer(f"📊 <b>Фидбек по диалогу:</b>\n\n{feedback}", reply_markup=keyboard, parse_mode="HTML")
    await message.answer("Ролевая игра завершена.", reply_markup=ReplyKeyboardRemove())

# ---------- ГОЛОСОВЫЕ СООБЩЕНИЯ ----------
@router.message(RoleplayStates.active, F.voice | F.audio)
async def handle_voice_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "roleplay_active":
        await message.answer("Вы не в режиме ролевой игры.")
        return

    logger.info(f"Voice message from user {user_id}")

    try:
        audio_obj = message.voice or message.audio
        if audio_obj is None:
            await message.answer("Не удалось найти аудиофайл.")
            return
        file = await message.bot.get_file(audio_obj.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        text = await voice_to_text(file_bytes.read())
    except Exception as e:
        logger.error(f"Ошибка распознавания: {e}")
        await message.answer("Не удалось распознать голосовое сообщение. Попробуйте написать текстом.")
        return

    if not text:
        await message.answer("Не удалось распознать речь. Попробуйте сказать чётче или напишите текстом.")
        return

    if is_forbidden(text):
        await message.answer("Пожалуйста, не отходите от темы диалога. Давайте продолжим ролевую игру в рамках заданной ситуации.")
        return

    if is_cyrillic(text):
        counter = user_state.get("russian_counter", 0) + 1
        user_state["russian_counter"] = counter
        set_user_state(user_id, user_state)
        show_english_reminder = (counter % 5 == 0)
    else:
        show_english_reminder = False

    topic = user_state.get("roleplay_topic", "")
    description = user_state.get("roleplay_description", "")
    goals = user_state.get("roleplay_goals", [])
    system_prompt = build_system_prompt(topic, description, goals)
    history = user_state.get("roleplay_history", [])
    ai_response = await call_ai_with_system(system_prompt, text, history)

    if show_english_reminder:
        ai_response += "\n\nFeel free to use English!"

    history.append({"role": "user", "text": text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["roleplay_history"] = history
    set_user_state(user_id, user_state)

    await message.answer(ai_response)

# ---------- ТЕКСТОВЫЕ СООБЩЕНИЯ ----------
@router.message(RoleplayStates.active, F.text)
async def handle_roleplay_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "roleplay_active":
        return

    user_text = message.text
    logger.info(f"User {user_id} sent text: {user_text[:30]}...")

    if is_forbidden(user_text):
        await message.answer("Пожалуйста, не отходите от темы диалога. Давайте продолжим ролевую игру в рамках заданной ситуации.")
        return

    if is_cyrillic(user_text):
        counter = user_state.get("russian_counter", 0) + 1
        user_state["russian_counter"] = counter
        set_user_state(user_id, user_state)
        show_english_reminder = (counter % 5 == 0)
    else:
        show_english_reminder = False

    topic = user_state.get("roleplay_topic", "")
    description = user_state.get("roleplay_description", "")
    goals = user_state.get("roleplay_goals", [])
    system_prompt = build_system_prompt(topic, description, goals)
    history = user_state.get("roleplay_history", [])
    ai_response = await call_ai_with_system(system_prompt, user_text, history)

    if show_english_reminder:
        ai_response += "\n\nFeel free to use English!"

    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["roleplay_history"] = history
    set_user_state(user_id, user_state)

    await message.answer(ai_response)

# ---------- ПОДСКАЗКА ----------
@router.message(RoleplayStates.active, F.text == "💡 Что ответить?")
async def give_hint(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("roleplay_history", [])
    if not history:
        await message.answer("Вы ещё не начали диалог. Начните разговор, чтобы получить подсказку.")
        return

    last_bot_msg = None
    if history and history[-1].get("role") == "assistant":
        last_bot_msg = history[-1].get("text", "")

    history_str = "\n".join([f"{msg['role']}: {msg['text']}" for msg in history[-5:]]) if history else "Нет истории"

    prompt = (
        "Ты – помощник в ролевой игре. Пользователь просит подсказку, что можно ответить дальше.\n"
        "Контекст диалога (последние сообщения):\n" + history_str + "\n"
        "Последнее сообщение бота: " + (last_bot_msg or "Нет сообщения") + "\n"
        "Предложи 2–3 варианта того, что пользователь может сказать или спросить в этой ситуации.\n"
        "Ответы должны быть на русском, естественные, соответствовать роли и ситуации."
    )
    try:
        hint = await chat(prompt, max_tokens=200, temperature=0.7)
    except Exception as e:
        logger.error(f"Ошибка получения подсказки: {e}")
        await message.answer("Не удалось получить подсказку. Попробуйте позже.")
        return
    await message.answer(f"💡 <b>Идеи для ответа:</b>\n\n{hint}", parse_mode="HTML")

# ---------- ГЛАВНОЕ МЕНЮ (КНОПКА) ----------
@router.message(RoleplayStates.active, F.text == "🏠 Главное меню")
async def exit_to_main_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    user_state["roleplay_history"] = []
    user_state["russian_counter"] = 0
    set_user_state(user_id, user_state)
    await state.clear()
    await message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False, remove_keyboard=True)