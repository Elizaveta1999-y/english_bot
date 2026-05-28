import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from data.users import set_user_state, get_user_state
from speaking.services.tts import text_to_voice
from speaking.services.ai import chat, is_safe_message

router = Router()

WELCOME_TEXT = (
    "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
    "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
    "Выбирай режим и начни совершенствоваться в языке!\n\n"
    "🌟 <b>Акция</b> – полный доступ ко всему функционалу <b>399₽/мес</b>."
)

CATEGORIES = [
    ("🏢 Работа и бизнес", "work"),
    ("✈️ Путешествия", "travel"),
    ("🍽️ Повседневная жизнь", "daily"),
    ("📚 Развлечения и хобби", "hobby"),
    ("👨‍⚕️ Здоровье", "health"),
    ("🏠 Дом и семья", "family"),
    ("📱 Технологии", "tech")
]

TOPICS = {
    "work": [
        {"name": "Собеседование на работу", "description": "Вы проходите собеседование на работу.", "goals": ["Опишите опыт работы.", "Расскажите о навыках.", "Объясните, почему вы подходите."]},
        {"name": "Переговоры с клиентом", "description": "Деловые переговоры с клиентом.", "goals": ["Представьте предложение.", "Ответьте на возражения.", "Договоритесь об условиях."]},
        {"name": "Презентация проекта", "description": "Вы проводите презентацию проекта.", "goals": ["Опишите суть.", "Перечислите преимущества.", "Ответьте на вопросы."]},
        {"name": "Разговор с начальником", "description": "Обсуждаете повышение или отпуск.", "goals": ["Сформулируйте просьбу.", "Аргументируйте.", "Предложите компромисс."]},
        {"name": "Ежедневный планер", "description": "План задач на день.", "goals": ["Перечислите задачи.", "Уточните приоритеты.", "Согласуйте дедлайны."]},
        {"name": "Оценка производительности", "description": "Ежегодный обзор.", "goals": ["Оцените достижения.", "Укажите зоны роста.", "Поставьте цели."]}
    ],
    "travel": [
        {"name": "Заказ такси в аэропорту", "description": "Звоните в службу такси.", "goals": ["Назовите адрес.", "Укажите время.", "Уточните стоимость."]},
        {"name": "Регистрация на рейс", "description": "Вы в аэропорту.", "goals": ["Предъявите паспорт.", "Сдайте багаж.", "Попросите место у окна."]},
        {"name": "Замена номера в отеле", "description": "Вам не подходит номер.", "goals": ["Объясните причину.", "Попросите другой номер.", "Уточните доплату."]},
        {"name": "Покупка сувениров", "description": "Вы на рынке.", "goals": ["Спросите цену.", "Поторгуйтесь.", "Оплатите."]},
        {"name": "Спросить дорогу у местного", "description": "Вы заблудились.", "goals": ["Поздоровайтесь.", "Назовите пункт назначения.", "Уточните путь."]},
        {"name": "Бронирование отеля онлайн", "description": "Звоните в отель.", "goals": ["Назовите даты.", "Уточните цену.", "Спросите про отмену."]},
        {"name": "Потеря багажа", "description": "В аэропорту.", "goals": ["Опишите чемодан.", "Сообщите номер рейса.", "Уточните статус."]}
    ],
    "daily": [
        {"name": "Заказ в ресторане", "description": "Вы в ресторане.", "goals": ["Попросите меню.", "Сделайте заказ.", "Попросите счёт."]},
        {"name": "Визит к врачу", "description": "На приёме у врача.", "goals": ["Опишите симптомы.", "Ответьте на вопросы.", "Уточните лечение."]},
        {"name": "Звонок в техподдержку", "description": "Проблема с интернетом.", "goals": ["Опишите проблему.", "Ответьте на вопросы.", "Следуйте инструкциям."]},
        {"name": "Разговор с соседом", "description": "Встретили соседа.", "goals": ["Поздоровайтесь.", "Поддержите беседу.", "Вежливо попрощайтесь."]},
        {"name": "Покупка продуктов в супермаркете", "description": "Вы в супермаркете.", "goals": ["Спросите отдел.", "Уточните цену.", "Оплатите на кассе."]},
        {"name": "Запись в спортзал", "description": "Звоните в фитнес-клуб.", "goals": ["Спросите абонементы.", "Уточните расписание.", "Запишитесь на пробную."]},
        {"name": "Ремонт техники", "description": "Сдаёте телефон в ремонт.", "goals": ["Опишите неисправность.", "Спросите стоимость.", "Оставьте контакты."]}
    ],
    "hobby": [
        {"name": "Обсуждение любимой книги", "description": "Обсуждаете книгу.", "goals": ["Назовите книгу.", "Расскажите о впечатлениях.", "Спросите мнение."]},
        {"name": "Спор о фильме", "description": "Спорите о фильме.", "goals": ["Изложите сюжет.", "Назовите плюсы/минусы.", "Спросите мнение."]},
        {"name": "Планы на выходные", "description": "Договариваетесь о встрече.", "goals": ["Предложите идеи.", "Обсудите время.", "Подтвердите."]},
        {"name": "Любимые рецепты", "description": "Делитесь рецептом.", "goals": ["Назовите блюдо.", "Опишите процесс.", "Дайте совет."]},
        {"name": "Совет по видеоигре", "description": "Просите совета.", "goals": ["Назовите игру.", "Спросите сложные моменты.", "Попросите подсказку."]},
        {"name": "Обсуждение музыки", "description": "Обсуждаете музыку.", "goals": ["Назовите исполнителя.", "Расскажите, почему нравится.", "Спросите о вкусах."]}
    ],
    "health": [
        {"name": "Запись к врачу по телефону", "description": "Звоните в поликлинику.", "goals": ["Назовите данные.", "Опишите симптомы.", "Выберите время."]},
        {"name": "Разговор с фармацевтом", "description": "В аптеке.", "goals": ["Опишите симптомы.", "Спросите о лекарстве.", "Уточните дозировку."]},
        {"name": "Скорая помощь", "description": "Звоните в скорую.", "goals": ["Назовите адрес.", "Опишите происшествие.", "Ответьте на вопросы."]},
        {"name": "Разговор с психологом", "description": "На сессии.", "goals": ["Расскажите о проблеме.", "Ответьте на вопросы.", "Попросите совет."]}
    ],
    "family": [
        {"name": "Разговор с родителями", "description": "Звоните родителям.", "goals": ["Поздоровайтесь.", "Расскажите новости.", "Спросите о здоровье."]},
        {"name": "Планы с детьми", "description": "Обсуждаете выходные.", "goals": ["Предложите варианты.", "Согласуйте время.", "Распределите обязанности."]},
        {"name": "Семейный ужин", "description": "Готовите ужин.", "goals": ["Спросите пожелания.", "Обсудите блюда.", "Договоритесь о времени."]}
    ],
    "tech": [
        {"name": "Настройка нового устройства", "description": "Звоните в поддержку.", "goals": ["Назовите модель.", "Опишите проблему.", "Следуйте инструкциям."]},
        {"name": "Обсуждение софта с коллегой", "description": "Сравниваете программы.", "goals": ["Назовите программы.", "Сравните функции.", "Придите к решению."]},
        {"name": "Заказ детали для компьютера", "description": "Звоните в магазин.", "goals": ["Назовите деталь.", "Уточните наличие.", "Оформите заказ."]},
        {"name": "Консультация по кибербезопасности", "description": "Консультируетесь.", "goals": ["Опишите угрозу.", "Спросите о защите.", "Запишите рекомендации."]}
    ]
}

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")],
        [InlineKeyboardButton(text="🎭 RolePlay", callback_data="start_roleplay")]
    ])
    await message.answer(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    await activate_speaking_mode(callback.message, user_id)

async def activate_speaking_mode(message: Message, user_id: int):
    set_user_state(user_id, {"mode": "speaking_active", "history": [], "roleplay_topic": None})
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Я всё! Фидбек")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"🎤 <b>Голосовой режим активирован!</b>\n\n"
        "Говори развёрнуто – так эффективнее для изучения! 🗣️",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    voice_greeting = "Hello! I am your AI English teacher. Send a voice message and we'll start practicing. Speak clearly!"
    voice_path = await text_to_voice(voice_greeting)
    if not voice_path:
        return
    with open(voice_path, 'rb') as f:
        audio_bytes = f.read()
    os.unlink(voice_path)
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_greeting_{user_id}")]
    ])
    sent_audio = await message.answer_audio(
        BufferedInputFile(audio_bytes, filename='greeting.ogg'),
        caption="",
        reply_markup=inline_keyboard
    )
    user_state = get_user_state(user_id)
    user_state["greeting_audio_id"] = sent_audio.message_id
    user_state["greeting_text"] = voice_greeting
    set_user_state(user_id, user_state)

@router.callback_query(lambda c: c.data == "start_roleplay")
async def start_roleplay_callback(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.answer(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.\n\n"
        "Бот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "custom_scenario")
async def custom_scenario_start(callback: CallbackQuery):
    await callback.message.answer(
        "✍️ <b>Придумайте свой сценарий</b>\n\n"
        "Опишите ситуацию и роль бота одним сообщением.\n"
        "Пример:\n"
        "<i>Ты продавец в книжном магазине. Я покупатель, ищу книгу по фантастике. Ты предлагаешь новинки и помогаешь выбрать.</i>\n\n"
        "Напишите ваш сценарий:",
        parse_mode="HTML"
    )
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = True
    set_user_state(user_id, user_state)
    await callback.answer()

@router.message(F.text)
async def process_custom_scenario(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if not user_state.get("awaiting_custom_scenario"):
        return
    user_state["awaiting_custom_scenario"] = False
    
    scenario_text = message.text
    
    # === ПРОВЕРКА БЕЗОПАСНОСТИ ===
    from speaking.services.ai import is_safe_message
    if not await is_safe_message(scenario_text):
        await message.answer(
            "❌ Ваш сценарий содержит неприемлемые темы. Пожалуйста, создайте другой сценарий."
            "Например, обыграйте ситуацию в кафе, аэропорту, на собеседовании или с книжным магазином",
            parse_mode="HTML"
        )
        set_user_state(user_id, user_state)
        return
    
    topic = scenario_text[:50] + ("..." if len(scenario_text) > 50 else "")
    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": "custom",
        "custom_scenario": scenario_text
    })
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Завершить диалог")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"🎭 <b>Ролевая игра: {topic}</b>\n\n"
        f"<b>Ваш сценарий:</b> {scenario_text}\n\n"
        f"🗣️ <b>Говорите голосом или пишите текстом.</b>\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?».\n"
        f"Когда закончите, нажмите «📊 Завершить диалог» для анализа.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await message.answer("🎬 <b>Можете начинать!</b>", parse_mode="HTML")

@router.callback_query(lambda c: c.data.startswith("cat_"))
async def show_topics(callback: CallbackQuery):
    cat_id = callback.data[4:]
    topics_list = TOPICS.get(cat_id, [])
    if not topics_list:
        await callback.answer("Нет тем в этой категории", show_alert=True)
        return
    buttons = []
    for idx, topic_info in enumerate(topics_list):
        buttons.append([InlineKeyboardButton(text=topic_info["name"], callback_data=f"topic_{cat_id}_{idx}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories")])
    topics_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    cat_display = next((c[0] for c in CATEGORIES if c[1] == cat_id), cat_id)
    await callback.message.edit_text(
        f"🎭 <b>{cat_display}</b>\n\nВыберите тему:",
        reply_markup=topics_keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.edit_text(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.\n\n"
        "Бот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("topic_"))
async def topic_chosen(callback: CallbackQuery):
    _, cat_id, idx_str = callback.data.split("_")
    idx = int(idx_str)
    topics_list = TOPICS.get(cat_id, [])
    if idx >= len(topics_list):
        await callback.answer("Тема не найдена", show_alert=True)
        return
    topic_info = topics_list[idx]
    topic = topic_info["name"]
    description = topic_info["description"]
    goals = topic_info["goals"]
    user_id = callback.from_user.id
    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": cat_id
    })
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
        f"<b>📖 Ситуация:</b> {description}\n\n"
        f"<b>🎯 Ваши цели:</b>\n{goals_text}\n\n"
        f"🗣️ <b>Говорите голосом или пишите текстом.</b>\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?».\n"
        f"Когда закончите, нажмите «📊 Завершить диалог» для анализа."
    )
    await callback.message.edit_text(roleplay_info, parse_mode="HTML")
    await callback.message.answer("🎬 <b>Можете начинать!</b>", reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "💡 Что ответить?")
async def hint_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    if mode != "roleplay_active":
        await message.answer("Эта кнопка доступна только в режиме ролевой игры.")
        return
    topic = user_state.get("roleplay_topic")
    history = user_state.get("history", [])
    if not topic:
        await message.answer("Сначала выберите тему.")
        return
    context = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-5:]])
    prompt = f"Ты – участник ролевой игры (тема: {topic}). Пользователь не знает, что ответить. Дай 2–3 коротких варианта ответа (по-английски). Контекст:\n{context}\nОтветь только вариантами."
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    hints = chat(prompt, max_tokens=200, temperature=0.7)
    await message.answer(f"💡 Варианты ответа:\n{hints}", parse_mode="HTML")

@router.message(F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    if mode != "roleplay_active":
        await message.answer("Эта кнопка доступна только в ролевой игре.")
        return
    history = user_state.get("history", [])
    user_messages = [h for h in history if h.get("role") == "user" and h.get("text", "").strip()]
    if len(user_messages) < 3:
        needed = 3 - len(user_messages)
        await message.answer(
            f"📭 Вы ещё не общались по сценарию. Отправьте ещё {needed} сообщения (нужно минимум 3). Пожалуйста, продолжите диалог по сценарию."
        )
        return
    processing_msg = await message.answer("🔄 Генерирую анализ диалога... Подождите немного.")
    conversation = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-20:]])
    topic = user_state.get("roleplay_topic", "ролевая игра")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    prompt = (
        f"Ты опытный преподаватель английского. Проанализируй диалог в ролевой игре на тему '{topic}'. "
        "Дай фидбек на русском языке, не более 7-8 предложений. "
        "Сначала коротко похвали ученика (1 предложение). "
        "Затем перечисли конкретные грамматические и лексические ошибки (2-3 примера). "
        "Для каждой ошибки напиши: что было неправильно, как правильно, краткое пояснение (1 фраза). "
        "После этого дай один общий совет (1 предложение). "
        "Не пиши 'фидбек для вас как для преподавателя'. Используй HTML-теги <b> и <i>. Добавь смайлики.\n\n"
        f"Диалог:\n{conversation}"
    )
    feedback = chat(prompt, max_tokens=600, temperature=0.5)
    if len(feedback) > 1200:
        feedback = feedback[:1200] + "..."
    await processing_msg.edit_text(f"📊 Анализ диалога:\n\n{feedback}", parse_mode="HTML")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Продолжить диалог", callback_data="continue_roleplay")],
        [InlineKeyboardButton(text="🏠 Выйти в меню", callback_data="exit_to_menu")]
    ])
    await message.answer("Желаете продолжить ролевую игру или завершить?", reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "continue_roleplay")
async def continue_roleplay(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Продолжаем.")

@router.callback_query(lambda c: c.data == "exit_to_menu")
async def exit_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    await callback.message.answer("Режим завершён. Нажмите /start для выбора режима.", reply_markup=ReplyKeyboardRemove())
    await callback.answer()

@router.message(F.text == "📊 Я всё! Фидбек")
async def feedback_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    if mode != "speaking_active":
        await message.answer("Фидбек доступен только в режиме Speaking.")
        return
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("Вы ещё не общались. Отправьте несколько голосовых сообщений.")
        return
    conversation = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    prompt = (
        "Ты учитель английского. Дай короткий фидбек (до 5 предложений) на русском языке. "
        "Сначала похвали, потом перечисли основные ошибки (с исправлениями), дай совет. "
        "Используй HTML-теги <b> и <i>. Добавь смайлики.\n\n"
        f"Диалог:\n{conversation}"
    )
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    feedback = chat(prompt, max_tokens=500, temperature=0.5)
    if len(feedback) > 1000:
        feedback = feedback[:1000] + "..."
    await message.answer(f"📊 Ваш фидбек:\n\n{feedback}", parse_mode="HTML")

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    if user_id in last_bot_response:
        del last_bot_response[user_id]
    if user_id in last_text_response:
        del last_text_response[user_id]
    await message.answer("Режим завершён. Нажмите /start для выбора режима.", reply_markup=ReplyKeyboardRemove())

# ---------- ОБРАБОТЧИКИ ДЛЯ ПРИВЕТСТВЕННОГО АУДИО (GREETING) ----------
@router.callback_query(lambda c: c.data.startswith("show_greeting_"))
async def show_greeting_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user_state = get_user_state(user_id)
    if "greeting_text" not in user_state:
        await callback.answer("No text available", show_alert=True)
        return
    original = user_state["greeting_text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_greeting_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=user_state["greeting_audio_id"],
        caption=f"📝 {original}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_greeting_"))
async def translate_greeting(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user_state = get_user_state(user_id)
    original = user_state.get("greeting_text")
    if not original:
        await callback.answer("No text", show_alert=True)
        return
    translation = chat(f"Translate to Russian: {original}", max_tokens=200, temperature=0.3)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"show_greeting_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_greeting_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=user_state["greeting_audio_id"],
        caption=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_greeting_"))
async def hide_greeting(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user_state = get_user_state(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_greeting_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=user_state["greeting_audio_id"],
        caption="",
        reply_markup=keyboard
    )
    await callback.answer()