import os
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from data.users import set_user_state
from speaking.services.tts import text_to_voice

router = Router()

# --- Главная клавиатура с тремя кнопками ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎤 Speaking")],
        [KeyboardButton(text="🇷🇺 Перевод"), KeyboardButton(text="🇬🇧 Оригинал")]
    ],
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
    set_user_state(user_id, {"waiting_for_name": True, "mode": "speaking_name"})

    await message.answer(
        "🎤 Voice mode activated!\n\nPlease say your name.",
        reply_markup=ReplyKeyboardRemove()  # убираем клавиатуру на время голосового общения
    )

    voice_greeting = "Hello! I am your voice AI English tutor. What should I call you?"
    voice_path = await text_to_voice(voice_greeting)
    if voice_path:
        from aiogram.types import FSInputFile
        await message.answer_voice(FSInputFile(voice_path))
        os.unlink(voice_path)