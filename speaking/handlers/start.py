from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from services.tts import text_to_voice
from services.storage import set_user_state, get_user_state

router = Router()


# 🔹 /start
@router.message(Command("start"))
async def start_handler(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Игры")],
            [KeyboardButton(text="📝 ОГЭ / ЕГЭ")],
            [KeyboardButton(text="🎤 Speaking")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Hello! 👋 Я твой персональный учитель английского 🇬🇧\n\n"
        "Выбери режим:",
        reply_markup=keyboard
    )


# 🔹 Нажатие на Speaking
@router.message(lambda message: message.text == "🎤 Speaking")
async def speaking_mode(message: Message):
    user_id = message.from_user.id

    # Включаем режим speaking
    set_user_state(user_id, {"mode": "speaking"})

    voice = await text_to_voice("""
Hello! I am Voice AI, your personal English tutor.
I'm here to help you practice speaking English, improve your grammar, and expand your vocabulary.
We'll communicate using our voices!
What should I call you?
""")

    await message.answer_voice(voice)


# 🔹 Блок текста в speaking режиме
@router.message()
async def block_text(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)

    if state.get("mode") == "speaking":
        await message.answer("Пожалуйста, отправь голосовое сообщение 🎤")