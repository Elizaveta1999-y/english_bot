from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 Игры", callback_data="games"),
        ],
        [
            InlineKeyboardButton(text="📝 ОГЭ / ЕГЭ", callback_data="exam"),
        ],
        [
            InlineKeyboardButton(text="🎤 Speaking", callback_data="speaking"),
        ]
    ])

    text = (
        "Hello!👋 Я твой персональный учитель английского 🇬🇧\n\n"
        "Я помогу тебе:\n"
        "— прокачать разговорный английский\n"
        "— подготовиться к экзаменам\n"
        "— играть и учить слова\n\n"
        "👇 Выбери режим:"
    )

    await message.answer(text, reply_markup=keyboard)