import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from data.users import set_user_state
from speaking.services.tts import text_to_voice

router = Router()

WELCOME_TEXT = (
    "Добро пожаловать в умный тренажер Английского языка! 🇺🇸\n\n"
    "Этот уникальный бот основан на базе ИИ, который будет твоим персональным тьютором. "
    "Буквально! он будет следить за твоим прогрессом, проходить с тобой уроки, проверять дз и общаться голосом! "
    "Интересно? Тогда выбирай режим и начнем совершенствоваться в языке! \n\n"
    "Полный доступ к всему функционалу всего за 399₽/мес. Дешевле билета в кино, но пользы на всю жизнь 🍿😎"
)

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")]
    ])
    await message.answer(WELCOME_TEXT, reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_state(user_id, {"mode": "speaking_active", "history": []})
    await callback.answer()
    await callback.message.answer(
        "🎤 Голосовой режим активирован!\n\n"
        "Просто отправь голосовое сообщение, и я помогу с произношением и грамматикой.\n"
        "После моего ответа под аудио появится кнопка «Текст» – нажми её, чтобы увидеть текст и перевести.\n"
        "Когда закончишь, можешь запросить фидбек.\n\n"
        "Говори развёрнуто – так эффективнее для изучения! 🗣️"
    )
    voice_greeting = "Hello! I am your AI English teacher. Send a voice message and we'll start practicing. Speak clearly!"
    voice_path = await text_to_voice(voice_greeting)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        await callback.message.answer_audio(BufferedInputFile(audio_bytes, filename='greeting.mp3'))
        os.unlink(voice_path)