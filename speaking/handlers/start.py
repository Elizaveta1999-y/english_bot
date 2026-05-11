import os
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.filters import Command
from data.users import set_user_state
from speaking.services.tts import text_to_voice

router = Router()

# Только одна кнопка для активации режима
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🎤 Speaking")]],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    await message.answer(
        "Hello! 🤖\n\nI'm your American English tutor.\n"
        "Press '🎤 Speaking' to start a voice lesson.",
        reply_markup=main_keyboard
    )

@router.message(F.text == "🎤 Speaking")
async def speaking_mode(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": "speaking_active", "history": []})
    await message.answer(
        "🎤 Voice mode activated!\n\nJust send a voice message. I'll correct your English.\n\n"
        "After my voice response, a button '📝 Текст' will appear – tap it to see the original text and then translate it.\n\nLet's begin! 🗣️",
        reply_markup=main_keyboard  # оставляем клавиатуру с одной кнопкой
    )
    # Голосовое приветствие (опционально)
    voice_greeting = "Hello! I am your voice AI English tutor. Just send a voice message and we'll start."
    voice_path = await text_to_voice(voice_greeting)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        await message.answer_voice(BufferedInputFile(audio_bytes, filename='greeting.mp3'))
        os.unlink(voice_path)