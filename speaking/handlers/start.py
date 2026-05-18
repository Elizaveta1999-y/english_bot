import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from data.users import set_user_state
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
    ("👨‍⚕️ Здоровье", "health")
]

TOPICS = {
    "work": [
        {"name": "Собеседование на работу", "description": "Вы проходите собеседование на работу. Вам нужно представить свои навыки, опыт и мотивацию.", "goals": ["Опишите свой предыдущий опыт работы.", "Расскажите о навыках, подходящих для этой должности.", "Объясните, почему вы хотите получить эту работу."]},
        {"name": "Переговоры с клиентом", "description": "Вы участвуете в деловых переговорах с потенциальным клиентом. Нужно обсудить условия сотрудничества, цену и сроки.", "goals": ["Представьте свою компанию и предложение.", "Ответьте на возражения клиента.", "Договоритесь о выгодных условиях."]},
        {"name": "Презентация проекта", "description": "Вы проводите презентацию своего проекта перед руководством. Нужно чётко изложить идею, преимущества и план реализации.", "goals": ["Кратко опишите суть проекта.", "Перечислите основные преимущества.", "Ответьте на вопросы слушателей."]},
        {"name": "Разговор с начальником", "description": "Вы обсуждаете с начальником свою работу, просите повышение или отпуск.", "goals": ["Чётко сформулируйте свою просьбу.", "Аргументируйте, почему вы её заслуживаете.", "Предложите компромисс или план действий."]}
    ],
    "travel": [
        {"name": "Заказ такси в аэропорту", "description": "Вы звоните в службу такси, чтобы заказать машину до аэропорта. Нужно назвать адрес, время и обсудить стоимость.", "goals": ["Назовите точный адрес подачи.", "Укажите желаемое время и количество пассажиров.", "Уточните стоимость и способ оплаты."]},
        {"name": "Регистрация на рейс", "description": "Вы находитесь в аэропорту и проходите регистрацию на рейс. Нужно предъявить документы, сдать багаж и получить посадочный талон.", "goals": ["Предъявите паспорт и билет.", "Сдайте багаж (укажите вес и количество мест).", "Попросите место у окна или у прохода."]},
        {"name": "Замена номера в отеле", "description": "Вы остановились в отеле, но номер вам не подходит (шумно, не работает кондиционер). Нужно попросить замену.", "goals": ["Объясните причину недовольства.", "Попросите другой номер (с лучшим видом, тихий).", "Уточните, возможна ли доплата за улучшение."]},
        {"name": "Покупка сувениров", "description": "Вы на рынке и хотите купить сувениры. Нужно узнать цену, поторговаться и оплатить покупку.", "goals": ["Спросите цену на понравившийся товар.", "Попробуйте сбить цену (поторгуйтесь).", "Оплатите и попросите чек."]},
        {"name": "Спросить дорогу у местного", "description": "Вы заблудились в незнакомом городе. Нужно вежливо спросить дорогу до нужного места.", "goals": ["Поздоровайтесь и извинитесь за беспокойство.", "Чётко назовите пункт назначения.", "Уточните, как лучше дойти (пешком или на транспорте)."]}
    ],
    "daily": [
        {"name": "Заказ в ресторане", "description": "Вы в ресторане, делаете заказ. Нужно попросить меню, выбрать блюда, уточнить состав и оплатить счёт.", "goals": ["Попросите меню и порекомендуйте фирменное блюдо.", "Сделайте заказ (учтите аллергии, предпочтения).", "Попросите счёт и оплатите."]},
        {"name": "Визит к врачу", "description": "Вы на приёме у врача. Нужно описать симптомы, ответить на вопросы и получить рекомендации.", "goals": ["Расскажите, что вас беспокоит (симптомы, когда началось).", "Ответьте на вопросы врача (аллергии, лекарства, образ жизни).", "Уточните диагноз и лечение."]},
        {"name": "Звонок в техподдержку", "description": "Вы звоните в техподдержку с проблемой (не работает интернет, завис компьютер). Нужно описать проблему и следовать инструкциям.", "goals": ["Чётко опишите проблему и когда она возникла.", "Ответьте на вопросы оператора (что пробовали сделать).", "Следуйте инструкциям по устранению."]},
        {"name": "Разговор с соседом", "description": "Вы встретили соседа в лифте или во дворе. Поддержите вежливую беседу о погоде, новостях или бытовых вопросах.", "goals": ["Поздоровайтесь и спросите, как дела.", "Поддержите беседу (погода, последние события).", "Вежливо попрощайтесь."]},
        {"name": "Покупка продуктов в супермаркете", "description": "Вы в супермаркете, выбираете продукты. Нужно найти нужный отдел, уточнить цену, оплатить на кассе.", "goals": ["Спросите, где находится нужный отдел.", "Уточните цену и срок годности.", "На кассе поздоровайтесь, оплатите и возьмите чек."]}
    ],
    "hobby": [
        {"name": "Обсуждение любимой книги", "description": "Вы обсуждаете с другом любимую книгу. Нужно поделиться впечатлениями, спросить мнение собеседника, порекомендовать другие произведения.", "goals": ["Назовите книгу и автора.", "Расскажите, что вам понравилось (герои, сюжет, стиль).", "Спросите, что читает собеседник, и порекомендуйте свою книгу."]},
        {"name": "Спор о фильме", "description": "Вы спорите с другом о фильме: один считает его шедевром, другой – провалом. Нужно аргументировать свою точку зрения.", "goals": ["Кратко изложите сюжет фильма.", "Назовите, что вам понравилось (или не понравилось) с примерами.", "Спросите мнение оппонента и попытайтесь его переубедить."]},
        {"name": "Планы на выходные", "description": "Вы обсуждаете с другом планы на выходные. Нужно предложить варианты, договориться о времени и месте встречи.", "goals": ["Предложите несколько идей (кино, прогулка, кафе).", "Обсудите время и место встречи.", "Подтвердите договорённости."]},
        {"name": "Любимые рецепты", "description": "Вы делитесь любимым рецептом с другом. Нужно назвать ингредиенты, описать процесс приготовления и поделиться секретами.", "goals": ["Назовите блюдо и список ингредиентов.", "Опишите основные шаги приготовления.", "Дайте совет или лайфхак."]}
    ],
    "health": [
        {"name": "Запись к врачу по телефону", "description": "Вы звоните в поликлинику, чтобы записаться к врачу. Нужно назвать свои данные, симптомы и выбрать удобное время.", "goals": ["Назовите свои ФИО и полис.", "Опишите причину визита (симптомы, жалобы).", "Выберите удобное время приёма."]},
        {"name": "Разговор с фармацевтом в аптеке", "description": "Вы в аптеке, хотите купить лекарство. Нужно описать симптомы, спросить о препаратах и уточнить дозировку.", "goals": ["Опишите, что вас беспокоит (боль, кашель, температура).", "Спросите, какое лекарство подойдёт.", "Уточните дозировку и возможные побочные эффекты."]}
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
    categories_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES
    ])
    await callback.message.answer(
        "🎭 <b>Выберите категорию для ролевой игры</b>\n\n"
        "Бот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=categories_keyboard,
        parse_mode="HTML"
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
    await callback.message.edit_text(
        f"🎭 <b>{cat_display}</b>\n\nВыберите тему:",
        reply_markup=topics_keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    categories_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES
    ])
    await callback.message.edit_text(
        "🎭 <b>Выберите категорию для ролевой игры</b>",
        reply_markup=categories_keyboard,
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
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )
    goals_text = "\n".join([f"{i+1}) {goal}" for i, goal in enumerate(goals)])
    roleplay_info = (
        f"🎭 <b>Ролевая игра: {topic}</b>\n\n"
        f"<b>📖 Ситуация:</b> {description}\n\n"
        f"<b>🎯 Ваши цели:</b>\n{goals_text}\n\n"
        f"🗣️ <b>Говорите голосом или пишите текстом.</b>\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?»."
    )
    await callback.message.answer(roleplay_info, reply_markup=keyboard, parse_mode="HTML")
    # Отдельное сообщение-приглашение
    await callback.message.answer("🎬 <b>Можете начинать!</b>", parse_mode="HTML")

# Обработчики для greeting (show_greeting_, translate_greeting_, hide_greeting_) должны быть здесь,
# но для краткости я их не копирую. В вашем реальном файле они уже есть.