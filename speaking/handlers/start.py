import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from data.users import set_user_state, get_user_state
from speaking.services.tts import text_to_voice
from speaking.services.ai import chat

router = Router()

WELCOME_TEXT = (
    "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
    "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
    "Выбирай режим и начни совершенствоваться в языке!\n\n"
    "🌟 <b>Акция</b> – полный доступ ко всему функционалу <s>700₽</s> <b>399₽/мес</b>."
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
        {"name": "Собеседование на работу", "description": "Вы проходите собеседование на работу. Вам нужно представить свои навыки, опыт и мотивацию.", "goals": ["Опишите свой предыдущий опыт работы.", "Расскажите о навыках, подходящих для этой должности.", "Объясните, почему вы хотите получить эту работу."]},
        {"name": "Переговоры с клиентом", "description": "Вы участвуете в деловых переговорах с потенциальным клиентом.", "goals": ["Представьте свою компанию и предложение.", "Ответьте на возражения клиента.", "Договоритесь о выгодных условиях."]},
        {"name": "Презентация проекта", "description": "Вы проводите презентацию своего проекта перед руководством.", "goals": ["Кратко опишите суть проекта.", "Перечислите преимущества.", "Ответьте на вопросы слушателей."]},
        {"name": "Разговор с начальником", "description": "Вы обсуждаете с начальником свою работу, просите повышение или отпуск.", "goals": ["Чётко сформулируйте просьбу.", "Аргументируйте, почему вы её заслуживаете.", "Предложите компромисс."]}
    ],
    "travel": [
        {"name": "Заказ такси в аэропорту", "description": "Вы звоните в службу такси, чтобы заказать машину до аэропорта.", "goals": ["Назовите точный адрес подачи.", "Укажите время и количество пассажиров.", "Уточните стоимость и способ оплаты."]},
        {"name": "Регистрация на рейс", "description": "Вы находитесь в аэропорту и проходите регистрацию на рейс.", "goals": ["Предъявите паспорт и билет.", "Сдайте багаж.", "Попросите место у окна."]},
        {"name": "Замена номера в отеле", "description": "Вам не подходит номер (шумно, не работает кондиционер).", "goals": ["Объясните причину недовольства.", "Попросите другой номер.", "Уточните возможность доплаты."]},
        {"name": "Покупка сувениров", "description": "Вы на рынке и хотите купить сувениры.", "goals": ["Спросите цену.", "Поторгуйтесь.", "Оплатите и попросите чек."]},
        {"name": "Спросить дорогу у местного", "description": "Вы заблудились в незнакомом городе.", "goals": ["Поздоровайтесь и извинитесь.", "Назовите пункт назначения.", "Уточните, как лучше дойти."]}
    ],
    "daily": [
        {"name": "Заказ в ресторане", "description": "Вы в ресторане, делаете заказ.", "goals": ["Попросите меню.", "Сделайте заказ (учтите аллергии).", "Попросите счёт."]},
        {"name": "Визит к врачу", "description": "Вы на приёме у врача.", "goals": ["Опишите симптомы.", "Ответьте на вопросы.", "Уточните диагноз и лечение."]},
        {"name": "Звонок в техподдержку", "description": "У вас проблема с интернетом или компьютером.", "goals": ["Опишите проблему.", "Ответьте на вопросы оператора.", "Следуйте инструкциям."]},
        {"name": "Разговор с соседом", "description": "Вы встретили соседа в лифте или во дворе.", "goals": ["Поздоровайтесь и спросите, как дела.", "Поддержите беседу (погода, новости).", "Вежливо попрощайтесь."]},
        {"name": "Покупка продуктов в супермаркете", "description": "Вы в супермаркете, выбираете продукты.", "goals": ["Спросите, где нужный отдел.", "Уточните цену и срок годности.", "Оплатите на кассе."]}
    ],
    "hobby": [
        {"name": "Обсуждение любимой книги", "description": "Вы обсуждаете с другом любимую книгу.", "goals": ["Назовите книгу и автора.", "Расскажите, что понравилось.", "Спросите, что читает собеседник."]},
        {"name": "Спор о фильме", "description": "Вы спорите с другом о фильме.", "goals": ["Изложите сюжет.", "Назовите, что понравилось/не понравилось.", "Спросите мнение оппонента."]},
        {"name": "Планы на выходные", "description": "Вы обсуждаете с другом планы на выходные.", "goals": ["Предложите идеи.", "Обсудите время и место.", "Подтвердите договорённости."]},
        {"name": "Любимые рецепты", "description": "Вы делитесь любимым рецептом с другом.", "goals": ["Назовите блюдо и ингредиенты.", "Опишите процесс.", "Дайте совет."]}
    ],
    "health": [
        {"name": "Запись к врачу по телефону", "description": "Вы звоните в поликлинику, чтобы записаться к врачу.", "goals": ["Назовите свои данные и полис.", "Опишите причину визита.", "Выберите время."]},
        {"name": "Разговор с фармацевтом в аптеке", "description": "Вы хотите купить лекарство.", "goals": ["Опишите симптомы.", "Спросите, какое лекарство подойдёт.", "Уточните дозировку и побочные эффекты."]}
    ],
    "family": [
        {"name": "Разговор с родителями", "description": "Вы звоните родителям, чтобы обсудить семейные дела.", "goals": ["Поздоровайтесь и спросите о здоровье.", "Расскажите о своих новостях.", "Попросите совета по семейному вопросу."]},
        {"name": "Планы с детьми", "description": "Вы обсуждаете с супругом/ой планы с детьми на выходные.", "goals": ["Предложите варианты.", "Согласуйте время и бюджет.", "Распределите обязанности."]}
    ],
    "tech": [
        {"name": "Настройка нового устройства", "description": "Вы звоните в поддержку, чтобы настроить новое устройство.", "goals": ["Назовите модель устройства.", "Опишите проблему при настройке.", "Следуйте инструкциям оператора."]},
        {"name": "Обсуждение софта с коллегой", "description": "Вы обсуждаете с коллегой преимущества разных программ.", "goals": ["Назовите программы.", "Сравните их функции.", "Придите к общему решению."]}
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
    set_user_state(user_id, user_state)

    scenario_text = message.text
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

# Обработчики для greeting (show_greeting_, translate_greeting_, hide_greeting_) должны быть, но для краткости опущены. Они есть в предыдущих версиях.