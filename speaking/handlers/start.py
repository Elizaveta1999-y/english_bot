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

# Словарь категорий и тем (с идентификаторами)
CATEGORIES = [
    ("🏢 Работа и бизнес", "work"),
    ("✈️ Путешествия", "travel"),
    ("🍽️ Повседневная жизнь", "daily"),
    ("📚 Развлечения и хобби", "hobby")
]

TOPICS = {
    "work": [
        "Собеседование на работу",
        "Переговоры с клиентом",
        "Презентация проекта",
        "Разговор с начальником"
    ],
    "travel": [
        "Заказ такси в аэропорту",
        "Регистрация на рейс",
        "Замена номера в отеле",
        "Покупка сувениров",
        "Спросить дорогу у местного"
    ],
    "daily": [
        "Заказ в ресторане",
        "Визит к врачу",
        "Звонок в техподдержку",
        "Разговор с соседом",
        "Покупка продуктов в супермаркете"
    ],
    "hobby": [
        "Обсуждение любимой книги",
        "Спор о фильме",
        "Планы на выходные",
        "Любимые рецепты"
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
    """Активирует обычный голосовой режим (без роли)."""
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
    """Показывает категории для ролевых игр."""
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
    cat_id = callback.data[4:]  # убираем "cat_"
    topics = TOPICS.get(cat_id, [])
    if not topics:
        await callback.answer("Нет тем в этой категории", show_alert=True)
        return
    # Строим кнопки с topic_id (индекс)
    buttons = []
    for idx, topic_name in enumerate(topics):
        buttons.append([InlineKeyboardButton(text=topic_name, callback_data=f"topic_{cat_id}_{idx}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories")])
    topics_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    # Получаем отображаемое название категории
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
    topics = TOPICS.get(cat_id, [])
    if idx >= len(topics):
        await callback.answer("Тема не найдена", show_alert=True)
        return
    topic = topics[idx]
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
    await callback.message.answer(
        f"🎭 <b>Ролевая игра: {topic}</b>\n\n"
        f"Бот будет играть роль по сценарию. Говорите голосом или пишите текстом.\n"
        f"Если нужна подсказка, нажмите «💡 Что ответить?».\n\n"
        f"<i>Давайте начнём!</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await send_roleplay_start(callback.message, user_id, topic)

async def send_roleplay_start(message: Message, user_id: int, topic: str):
    """Генерирует первую реплику бота по выбранной теме."""
    from services.deepseek import chat
    prompt = f"""Ты – участник ролевой игры на английском языке. Тема: {topic}.
Напиши первую реплику от твоего персонажа, чтобы начать диалог. Реплика должна быть естественной, на английском языке, не более 2 предложений. Не добавляй пояснений, только саму реплику."""
    response = chat(prompt, max_tokens=100, temperature=0.7)
    await message.answer(response)

# --- Обработчики для кнопок приветственного аудио (greeting) ---
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