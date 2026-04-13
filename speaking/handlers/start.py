from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

from speaking.services.tts import text_to_voice
from speaking.services.storage import set_user_state, get_user_state

router = Router()


# 🔹 /start
@router.message(Command("start"))
async def start_handler(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
            [InlineKeyboardButton(text="📝 ОГЭ / ЕГЭ", callback_data="exam")],
            [InlineKeyboardButton(text="🎤 Speaking", callback_data="speaking")]
        ]
    )

    await message.answer(
        "Hello! 👋 Я твой персональный учитель английского 🇬🇧\n\nВыбери режим:",
        reply_markup=keyboard
    )


# 🔹 Speaking (через callback!)
@router.callback_query(lambda c: c.data == "speaking")
async def speaking_mode(callback: CallbackQuery):
    user_id = callback.from_user.id

    set_user_state(user_id, {"mode": "speaking"})

    voice = await text_to_voice("""
Hello! I am Voice AI, your personal English tutor.
I'm here to help you practice speaking English.
We'll communicate using our voices!
What should I call you?
""")

    await callback.message.answer_voice(voice)
    await callback.answer()


# 🔹 Блок текста
@router.message(lambda message: message.text is not None)
async def block_text(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)

    if state.get("mode") == "speaking":
        await message.answer("Пожалуйста, отправь голосовое сообщение 🎤")