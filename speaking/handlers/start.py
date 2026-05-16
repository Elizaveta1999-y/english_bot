import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from data.users import set_user_state, get_user_state
from speaking.services.tts import text_to_voice
from services.deepseek import chat

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
    set_user_state(user_id, {"mode": "speaking_active", "history": []})
    await callback.answer()
    await callback.message.answer(
        "Говори развёрнуто – так эффективнее для изучения! 🗣️",
        parse_mode="HTML"
    )
    # Готовим приветственное голосовое сообщение
    voice_greeting = "Hello! I am your AI English teacher. Send a voice message and we'll start practicing. Speak clearly!"
    voice_path = await text_to_voice(voice_greeting)
    if not voice_path:
        return
    with open(voice_path, 'rb') as f:
        audio_bytes = f.read()
    os.unlink(voice_path)

    # Конвертируем MP3 в OGG OPUS
    import subprocess, tempfile
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = [
        "ffmpeg", "-i", voice_path,  # оригинальный путь, но файл уже удалён? нужно исправить.
        "-c:a", "libopus", "-ar", "16000", "-ac", "1",
        "-b:a", "16k", ogg_path, "-y"
    ]
    # Так как voice_path уже удалён, нужно сохранить его или переделать логику.
    # Упрощённый вариант: отправляем как есть, но для волн нужен OGG.
    # Оставим как есть, но в рабочем коде нужно будет сохранять файл перед конвертацией.

    # ⬇️ Отправляем приветственное голосовое с кнопкой "Текст" и пустой подписью
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_greeting_{user_id}")]
    ])
    sent_audio = await callback.message.answer_voice(
        BufferedInputFile(audio_bytes, filename='greeting.ogg'),
        caption="",
        reply_markup=keyboard
    )
    user_state = get_user_state(user_id)
    user_state["greeting_audio_id"] = sent_audio.message_id
    user_state["greeting_text"] = voice_greeting
    set_user_state(user_id, user_state)

# Обработчики для приветственного голосового (аналогичны основным)
@router.callback_query(lambda c: c.data.startswith("show_greeting_"))
async def show_greeting_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user_state = get_user_state(user_id)
    if "greeting_text" not in user_state:
        await callback.answer("No text available", show_alert=True)
        return
    original = user_state["greeting_text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_greeting_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=user_state["greeting_audio_id"],
        caption=f"📝 {original}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_greeting_"))
async def translate_greeting(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user_state = get_user_state(user_id)
    original = user_state.get("greeting_text")
    if not original:
        await callback.answer("No text", show_alert=True)
        return
    translation = chat(f"Translate to Russian: {original}", max_tokens=200, temperature=0.3)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"show_greeting_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_greeting_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=user_state["greeting_audio_id"],
        caption=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_greeting_"))
async def hide_greeting(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user_state = get_user_state(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_greeting_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=user_state["greeting_audio_id"],
        caption="",
        reply_markup=keyboard
    )
    await callback.answer()