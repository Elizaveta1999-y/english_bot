from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from data.users import set_user_state, get_user_state

router = Router()

# Клавиатура главного меню
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎤 Speaking")],
    ],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    # Сбрасываем состояние пользователя
    set_user_state(user_id, {})
    await message.answer(
        "Hello! 🤖\n\n"
        "I'm your personal English tutor. "
        "Press the button below to start a voice lesson.",
        reply_markup=main_keyboard
    )

@router.message(F.text == "🎤 Speaking")
async def speaking_command(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    # Переводим бота в режим ожидания имени
    user_state["waiting_for_name"] = True
    user_state["mode"] = "speaking_name"

    # Текстовое приветствие с инструкцией
    await message.answer(
        "🎤 Voice mode activated!\n\n"
        "I am a friendly and patient voice AI English tutor.\n"
        "I will help you practice speaking English. Our conversation will be by voice only.\n\n"
        "Please say your name.",
        reply_markup=ReplyKeyboardRemove()
    )

    # Голосовое приветствие
    from speaking.services.tts import text_to_voice
    voice_greeting = "Hello! I am Voice AI, your personal voice English tutor. What should I call you?"
    voice_file = await text_to_voice(voice_greeting)
    if voice_file:
        await message.answer_voice(voice_file)