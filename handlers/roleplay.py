import re
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
from services.deepseek import chat
from speaking.services.ai import is_safe_message, process_roleplay_message, process_voice_message
from handlers.lesson_utils import check_answer
from states.reading_states import ReadingStates

router = Router()

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

# ========== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ТЕКСТА ==========
@router.message(F.text)
async def universal_text_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    # 1. Игнорируем, если активен режим аудирования
    if user_state.get("listening_active", False):
        return

    # 2. Игнорируем, если активны другие FSM-состояния (чтение, аудирование)
    current_state = await state.get_state()
    if current_state in [
        "ReadingStates:waiting_for_text",
        "ListeningState:answering_task",
        # можно добавить другие, если нужно
    ]:
        return

    # 3. Проверяем, что режим либо speaking, либо roleplay
    mode = user_state.get("mode")
    if mode not in ["speaking_active", "roleplay_active"]:
        return

    # Проверяем, что мы в режиме Speaking, и текст не является служебной кнопкой
    if mode == "speaking_active":
        if message.text not in ["📊 Я всё! Фидбек", "🏠 Главное меню"]:
            await message.answer(
                "🎙️ Давайте пообщаемся голосом!\nНажмите на значок микрофона и отправьте голосовое сообщение."
            )
            return

    print(f"[DEBUG] universal_text_handler: text={message.text}, lesson_qa_active={user_state.get('lesson_qa', {}).get('active')}")

    # 0. Обработка ответов в режиме практики (текст)
    if user_state.get("practice_lesson_key"):
        from handlers.lessons import show_practice_task, parse_user_answers
        lesson_key = user_state["practice_lesson_key"]
        practice = user_state.get("practice", {}).get(lesson_key)
        if not practice:
            return

        task_idx = practice.get("session_index", 0)
        tasks = practice.get("tasks", [])
        if task_idx >= len(tasks):
            await show_practice_task(message, user_id, edit=False)
            return

        task = tasks[task_idx]
        subtasks = task.get("subtasks", [])
        if not subtasks:
            await message.answer("Ошибка: нет подзаданий")
            return

        user_answers = parse_user_answers(message.text.strip(), len(subtasks))
        while len(user_answers) < len(subtasks):
            user_answers.append("")

        correct_count = 0
        wrong_list = []
        for i, subtask in enumerate(subtasks):
            user_ans = user_answers[i].strip() if i < len(user_answers) else ""
            correct = subtask.get("answer", "").strip()
            if user_ans.lower() == correct.lower():
                correct_count += 1
            else:
                wrong_list.append({
                    "question": subtask.get("question", ""),
                    "your": user_ans if user_ans else "(пусто)",
                    "correct": correct
                })

        practice["session_correct"] += correct_count
        practice["session_index"] += 1
        set_user_state(user_id, user_state)

        if not wrong_list:
            await message.answer(f"✅ Отлично! Все {len(subtasks)} ответов верны!")
        else:
            summary = f"❌ Правильно: {correct_count} из {len(subtasks)}\n\n"
            for w in wrong_list:
                summary += f"• {w['question']}\n   Ваш ответ: {w['your']} → правильно: {w['correct']}\n\n"
            await message.answer(summary)

        await show_practice_task(message, user_id, edit=False)
        return

    # 1. Обработка кастомного сценария
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

    # 2. Пропускаем служебные кнопки
    if message.text in ["💡 Что ответить?", "📊 Завершить диалог", "📊 Я всё! Фидбек"]:
        return

    # 3. ОБРАБОТКА ВОПРОСОВ ПО УРОКАМ
    if user_state.get("lesson_qa", {}).get("active"):
        from handlers.lessons import process_lesson_question
        await process_lesson_question(user_id, message.text, message.bot, message.chat.id)
        return

    # 4. Режим урока (тематический урок) – заглушка
    if user_state.get("lesson_mode") == "thematic" and user_state.get("lesson_step") == "awaiting_answer":
        task = user_state.get("lesson_task")
        if not task:
            await message.answer("Ошибка: задание не найдено. Начните урок заново.")
            return
        feedback = await check_answer(message.text, task)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать ещё раз", callback_data="retry_lesson")],
            [InlineKeyboardButton(text="📝 Следующее задание", callback_data="next_task")],
            [InlineKeyboardButton(text="❌ Завершить", callback_data="exit_lesson")]
        ])
        await message.answer(f"📊 Результат:\n\n{feedback}", reply_markup=keyboard)
        user_state["lesson_step"] = "feedback_shown"
        set_user_state(user_id, user_state)
        return

    # 5. Режим Speaking
    mode = user_state.get("mode")
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

    # 6. Режим RolePlay
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