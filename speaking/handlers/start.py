import os
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from data.users import set_user_state
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
        "Hello! 🤖\n\nI'm your personal English tutor.",
        reply_markup=main_keyboard
    )

@router.message(F.text == "🎤 Speaking")
async def speaking_mode(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": "speaking_active"})
    await message.answer(
        "🎤 Voice mode activated!\n\n"
        "Just send a voice message in English. I'll correct your mistakes and respond.\n\n"
        "Let's begin! 🗣️",
        reply_markup=ReplyKeyboardRemove()
    )
    voice_greeting = "Hello! I am your voice AI English tutor. Just send a voice message and we'll start practicing."
    voice_path = await text_to_voice(voice_greeting)
    if voice_path:
        with open(voice_path, 'rb') as audio_file:
            await message.answer_voice(audio_file, filename='response.mp3')
        os.unlink(voice_path)