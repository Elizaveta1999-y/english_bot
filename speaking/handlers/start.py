from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.filters import Command
from data.users import set_user_state, get_user_state
from speaking.services.tts import text_to_voice

router = Router()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🎤 Speaking")]],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    await message.answer(
        "Hello! 🤖\n\nI'm your personal English tutor. Press the button below to start a voice lesson.",
        reply_markup=main_keyboard
    )

@router.message(F.text == "🎤 Speaking")
async def speaking_command(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    user_state["waiting_for_name"] = True
    user_state["mode"] = "speaking_name"
    set_user_state(user_id, user_state)

    await message.answer(
        "🎤 Voice mode activated!\n\n"
        "I am a friendly and patient voice AI English tutor.\n"
        "I will help you practice speaking English. Our conversation will be by voice only.\n\n"
        "Please say your name.",
        reply_markup=ReplyKeyboardRemove()
    )

    voice_greeting = "Hello! I am Voice AI, your personal voice English tutor. What should I call you?"
    voice_path = await text_to_voice(voice_greeting)
    
    if voice_path:
        # Отправляем голосовое, используя FSInputFile
        voice_file = FSInputFile(voice_path)
        await message.answer_voice(voice_file)
    else:
        await message.answer("Could not generate voice response. Please try again.")