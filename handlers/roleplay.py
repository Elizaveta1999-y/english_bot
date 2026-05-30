import re
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from data.users import set_user_state, get_user_state
from services.deepseek import chat
from speaking.services.ai import is_safe_message, process_roleplay_message, process_voice_message

router = Router()

# ========== КАТЕГОРИИ И ТЕМЫ (сокращённо, вставьте свои полные) ==========
CATEGORIES = [
    ("🏢 Работа и бизнес", "work"),
    ("✈️ Путешествия", "travel"),
    ("🍽️ Повседневная жизнь", "daily"),
    ("📚 Развлечения и хобби", "hobby"),
    ("👨‍⚕️ Здоровье", "health"),
    ("🏠 Дом и семья", "family"),
    ("📱 Технологии", "tech")
]

TOPICS = { ... }  # ← вставьте сюда ваш полный словарь TOPICS из предыдущего сообщения

# ========== ОБРАБОТЧИКИ КНОПОК И КАТЕГОРИЙ (без изменений) ==========
@router.callback_query(lambda c: c.data == "start_roleplay")
async def start_roleplay(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.answer(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.\n\nБот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=keyboard, parse_mode="HTML"
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

@router.callback_query(lambda c: c.data == "retry_custom_scenario")
async def retry_custom_scenario(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = True
    set_user_state(user_id, user_state)
    await callback.message.answer(
        "✍️ <b>Придумайте свой сценарий</b>\n\n"
        "Опишите ситуацию и роль бота одним сообщением.\n"
        "Пример:\n"
        "<i>Ты продавец в книжном магазине. Я покупатель, ищу книгу по фантастике.</i>\n\n"
        "Напишите ваш сценарий:",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_categories_from_scenario")
async def back_to_categories_from_scenario(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = False
    set_user_state(user_id, user_state)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.answer(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

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
    await callback.message.edit_text(f"🎭 <b>{cat_display}</b>\n\nВыберите тему:", reply_markup=topics_keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.edit_text("🎭 <b>Выберите категорию</b> или создайте свой сценарий.", reply_markup=keyboard, parse_mode="HTML")
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
        f"📖 Ситуация: {description}\n\n"
        f"🎯 Ваши цели:\n{goals_text}\n\n"
        f"🗣️ <b>Говорите голосом или пишите текстом.</b>\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?».\n"
        f"Когда закончите, нажмите «📊 Завершить диалог» для анализа."
    )
    await callback.message.edit_text(roleplay_info, parse_mode="HTML")
    await callback.message.answer("🎬 <b>Можете начинать!</b>", reply_markup=keyboard, parse_mode="HTML")

# ---------- КНОПКИ РОЛЕВОЙ ИГРЫ ----------
@router.message(F.text == "💡 Что ответить?")
async def hint_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "roleplay_active":
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
    await message.answer(f"💡 <b>Варианты ответа</b>:\n{hints}", parse_mode="HTML")

@router.message(F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "roleplay_active":
        await message.answer("Эта кнопка доступна только в ролевой игре.")
        return
    history = user_state.get("history", [])
    user_messages = [h for h in history if h.get("role") == "user" and len(h.get("text", "").strip()) > 2]
    if len(user_messages) < 3:
        needed = 3 - len(user_messages)
        await message.answer(f"📭 Вы ещё не общались по сценарию. Отправьте ещё {needed} сообщения (нужно минимум 3).")
        return
    processing_msg = await message.answer("🔄 Генерирую анализ диалога... Подождите немного.")
    conversation = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-20:]])
    topic = user_state.get("roleplay_topic", "ролевая игра")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    prompt = (
        f"Ты опытный преподаватель английского. Проанализируй диалог в ролевой игре на тему '{topic}'. "
        "Дай фидбек на русском языке, не более 7-8 предложений. "
        "Сначала похвали, потом ошибки с исправлениями, потом совет. Используй <b> и <i>. Добавь смайлики.\n\n"
        f"Диалог:\n{conversation}"
    )
    feedback = chat(prompt, max_tokens=600, temperature=0.5)
    if len(feedback) > 1200:
        feedback = feedback[:1200] + "..."
    await processing_msg.edit_text(f"📊 <b>Анализ диалога</b>:\n\n{feedback}", parse_mode="HTML")
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

# ---------- ЕДИНЫЙ ОБРАБОТЧИК ТЕКСТА ДЛЯ ВСЕХ РЕЖИМОВ ----------
@router.message(F.text)
async def universal_text_handler(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    
    # 1. Обработка кастомного сценария (ожидание ввода)
    if user_state.get("awaiting_custom_scenario"):
        user_state["awaiting_custom_scenario"] = False
        scenario_text = message.text.strip()
        if len(scenario_text.split()) < 3:
            await message.answer("❌ <b>Сценарий слишком короткий</b>. Опишите подробнее (минимум 3 слова).", parse_mode="HTML")
            user_state["awaiting_custom_scenario"] = True
            set_user_state(user_id, user_state)
            return
        if not await is_safe_message(scenario_text):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="retry_custom_scenario")],
                [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_categories_from_scenario")]
            ])
            await message.answer(
                "❌ <b>Ваш сценарий содержит неприемлемые темы</b> (секс, насилие, суицид и т.п.).\n\n"
                "Пожалуйста, придумайте другой сценарий для ролевой игры.",
                reply_markup=keyboard, parse_mode="HTML"
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
            reply_markup=keyboard, parse_mode="HTML"
        )
        await message.answer("🎬 <b>Можете начинать!</b>", parse_mode="HTML")
        return
    
    # 2. Пропускаем служебные кнопки (они обработаны выше)
    if message.text in ["💡 Что ответить?", "📊 Завершить диалог", "🏠 Главное меню", "📊 Я всё! Фидбек"]:
        return
    
    mode = user_state.get("mode")
    
    # 3. Режим Speaking (текстовый ввод)
    if mode == "speaking_active":
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        ai_response = await process_voice_message(user_id, message.text)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
        ])
        sent = await message.answer(ai_response, reply_markup=keyboard)
        from handlers.voice import last_text_response as global_last_text_response
        global_last_text_response[user_id] = {"text": ai_response, "translation": None, "message_id": sent.message_id}
        history = user_state.get("history", [])
        history.append({"role": "user", "text": message.text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)
        return
    
    # 4. Режим RolePlay (текстовый ввод)
    if mode == "roleplay_active":
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        ai_response = await process_roleplay_message(user_id, message.text)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
        ])
        sent = await message.answer(ai_response, reply_markup=keyboard)
        from handlers.voice import last_text_response as global_last_text_response
        global_last_text_response[user_id] = {"text": ai_response, "translation": None, "message_id": sent.message_id}
        history = user_state.get("history", [])
        history.append({"role": "user", "text": message.text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)
        return
    
    # 5. Если режим не установлен – можно проигнорировать или ответить
    # await message.answer("Сначала выберите режим: /start")