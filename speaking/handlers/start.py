from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# храним пользователей в режиме speaking
speaking_users = set()

async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [InlineKeyboardButton(text="📝 ОГЭ / ЕГЭ", callback_data="exam")],
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="speaking")]
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


# 🔥 ОБРАБОТКА КНОПКИ
async def handle_buttons(call: CallbackQuery):
    user_id = call.from_user.id

    if call.data == "speaking":
        speaking_users.add(user_id)
        await call.message.answer("🎤 Режим speaking включен. Отправь голос!")

    elif call.data == "games":
        await call.message.answer("🎮 Игры скоро тут")

    elif call.data == "exam":
        await call.message.answer("📝 Экзамен скоро тут")