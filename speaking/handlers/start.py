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
    # Отправляем приветственное голосовое с кнопкой "Текст"
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
    # Сохраним ID аудио и текст для последующего редактирования
    # Используем глобальный словарь, но для простоты сохраним в data.users
    user_state = set_user_state(user_id, {})
    user_state["greeting_audio_id"] = sent_audio.message_id
    user_state["greeting_text"] = voice_greeting
    set_user_state(user_id, user_state)

@router.callback_query(lambda c: c.data.startswith("show_greeting_"))
async def show_greeting_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user_state = get_user_state(user_id)  # нужно импортировать get_user_state
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
    # Переводим через DeepSeek
    from services.deepseek import chat
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