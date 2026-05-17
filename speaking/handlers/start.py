import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from data.users import set_user_state, set_user_level, get_user_level
from speaking.services.tts import text_to_voice

router = Router()

WELCOME_TEXT = (
    "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
    "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
    "Выбирай режим и начни совершенствоваться в языке!\n\n"
    "🌟 <b>Акция</b> – полный доступ ко всему функционалу <s>700₽</s> <b>399₽/мес</b>."
)

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")]
    ])
    await message.answer(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    existing_level = get_user_level(user_id)
    if existing_level:
        await activate_speaking_mode(callback, user_id, existing_level)
    else:
        level_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="A0 (Beginner)", callback_data="level_A0"),
                InlineKeyboardButton(text="A1 (Elementary)", callback_data="level_A1"),
                InlineKeyboardButton(text="A2 (Pre‑Intermediate)", callback_data="level_A2")
            ],
            [
                InlineKeyboardButton(text="B1 (Intermediate)", callback_data="level_B1"),
                InlineKeyboardButton(text="B2 (Upper‑Intermediate)", callback_data="level_B2"),
                InlineKeyboardButton(text="C1 (Advanced)", callback_data="level_C1")
            ]
        ])
        await callback.message.answer(
            "🗣️ <b>Выберите ваш уровень английского</b>\n\n"
            "Бот будет подстраивать сложность речи под ваш выбор.\n"
            "Уровень можно будет изменить в любой момент в настройках.",
            reply_markup=level_keyboard,
            parse_mode="HTML"
        )
        await callback.answer()

@router.callback_query(lambda c: c.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery):
    user_id = callback.from_user.id
    level_code = callback.data.split("_")[1]
    set_user_level(user_id, level_code)
    await callback.answer(f"Выбран уровень {level_code}")
    await activate_speaking_mode(callback, user_id, level_code)

async def activate_speaking_mode(callback: CallbackQuery, user_id: int, level: str):
    set_user_state(user_id, {"mode": "speaking_active", "history": []})
    await callback.message.answer(
        f"🎤 <b>Голосовой режим активирован!</b> (Уровень: {level})\n\n"
        "Говори развёрнуто – так эффективнее для изучения! 🗣️",
        parse_mode="HTML"
    )
    voice_greeting = "Hello! I am your AI English teacher. Send a voice message and we'll start practicing. Speak clearly!"
    voice_path = await text_to_voice(voice_greeting)
    if not voice_path:
        return
    with open(voice_path, 'rb') as f:
        audio_bytes = f.read()
    os.unlink(voice_path)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_greeting_{user_id}")]
    ])
    sent_audio = await callback.message.answer_audio(
        BufferedInputFile(audio_bytes, filename='greeting.ogg'),
        caption="",
        reply_markup=keyboard
    )
    user_state = get_user_state(user_id)
    user_state["greeting_audio_id"] = sent_audio.message_id
    user_state["greeting_text"] = voice_greeting
    set_user_state(user_id, user_state)

# Обработчики для приветственного аудио (show_greeting_, translate_greeting_, hide_greeting_)
# они должны быть здесь, но для краткости я их не копирую из предыдущей версии – в реальном файле они есть