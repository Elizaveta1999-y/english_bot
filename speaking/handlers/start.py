import os
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.filters import Command
from data.users import set_user_state
from speaking.services.tts import text_to_voice

router = Router()

# Клавиатура с 4 кнопками
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎤 Speaking")],
        [KeyboardButton(text="🇺🇸 Original"), KeyboardButton(text="🇷🇺 Перевод")],
        [KeyboardButton(text="📊 Я всё! Фидбек")]
    ],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    await message.answer(
        "Hello! 🤖\n\nI'm your American English tutor.",
        reply_markup=main_keyboard
    )

@router.message(F.text == "🎤 Speaking")
async def speaking_mode(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": "speaking_active", "history": []})
    # Оставляем клавиатуру, не убираем
    await message.answer(
        "🎤 Voice mode activated!\n\nJust send a voice message. I'll correct your English.\n\nLet's begin! 🗣️",
        reply_markup=main_keyboard
    )
    # Голосовое приветствие (опционально, но код оставим)
    voice_greeting = "Hello! I am your voice AI English tutor. Just send a voice message and we'll start."
    voice_path = await text_to_voice(voice_greeting)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        await message.answer_voice(BufferedInputFile(audio_bytes, filename='greeting.mp3'))
        os.unlink(voice_path)