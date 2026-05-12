import os
import re
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

logger = logging.getLogger(__name__)
router = Router()
# Хранилище: {user_id: {"text": str, "translation": str, "audio_message_id": int}}
last_bot_response = {}

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    logger.info(f"Received voice from user {user_id}")
    user_state = get_user_state(user_id)

    # 1. Распознаём речь пользователя
    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())
    logger.info(f"Recognized text: {user_text}")

    if not user_text:
        await message.answer("Sorry, I didn't catch that. Could you repeat?")
        return

    # 2. Активируем режим speaking, если ещё не активирован
    if user_state.get("mode") != "speaking_active":
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)

    # 3. Сохраняем историю
    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    # 4. Обработка имени, если пользователь представился
    name_match = re.search(r"(?:my name is|i am|i'm|call me)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
    if name_match:
        name = name_match.group(1)
        set_user_name(user_id, name)
        user_text = re.sub(r"(?:my name is|i am|i'm|call me)\s+[A-Za-z]+", "", user_text, flags=re.IGNORECASE).strip()
        if not user_text:  # только имя, без продолжения
            response_text = f"Nice to meet you, {name}! Tell me something about yourself."
            await _send_audio_reply(message, response_text, user_id)
            history.append({"role": "assistant", "text": response_text})
            user_state["history"] = history
            set_user_state(user_id, user_state)
            last_bot_response[user_id] = {"text": response_text, "translation": None, "audio_message_id": None}
            return

    # 5. Генерируем ответ через DeepSeek
    ai_response = await process_voice_message(user_id, user_text)
    logger.info(f"AI response: {ai_response[:100]}...")
    await _send_audio_reply(message, ai_response, user_id)

    # 6. Сохраняем ответ в историю
    history.append({"role": "assistant", "text": ai_response})
    user_state["history"] = history
    set_user_state(user_id, user_state)
    last_bot_response[user_id] = {"text": ai_response, "translation": None, "audio_message_id": None}

async def _send_audio_reply(message: Message, text: str, user_id: int):
    """
    Генерирует MP3/OGG и отправляет как аудиосообщение с подписью (английский оригинал)
    и кнопкой 'Перевести'. Внешне выглядит как голосовое сообщение с волнами.
    """
    voice_path = await text_to_voice(text)
    if not voice_path:
        # fallback: отправить текст, если генерация голоса не удалась
        await message.answer(text)
        return

    # Читаем аудиофайл
    with open(voice_path, 'rb') as f:
        audio_bytes = f.read()
    os.unlink(voice_path)  # удаляем временный файл

    # Клавиатура с кнопкой "Перевести"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}")]
    ])

    # Отправляем аудио с подписью (caption) — текст виден прямо под сообщением
    sent_audio = await message.answer_audio(
        BufferedInputFile(audio_bytes, filename='response.mp3'),
        caption=f"📝 {text}",
        reply_markup=keyboard
    )
    # Сохраняем ID сообщения, чтобы потом редактировать caption
    if user_id in last_bot_response:
        last_bot_response[user_id]["audio_message_id"] = sent_audio.message_id
    else:
        last_bot_response[user_id] = {"text": text, "translation": None, "audio_message_id": sent_audio.message_id}

@router.callback_query(lambda c: c.data.startswith("translate_"))
async def translate_caption(callback: CallbackQuery):
    """Переводит английскую подпись на русский и меняет кнопки."""
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No text to translate.", show_alert=True)
        return

    # Получаем или генерируем перевод
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(
            f"Translate the following English text to Russian. Output only the translation, no extras.\n\n{data['text']}",
            max_tokens=300, temperature=0.3
        )
        data["translation"] = translation
        last_bot_response[user_id] = data

    # Новая клавиатура: вернуть оригинал или скрыть
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")
        ]
    ])

    # Редактируем подпись (caption) того же сообщения
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_"))
async def revert_to_original(callback: CallbackQuery):
    """Возвращает английский оригинал в caption."""
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No original text.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"📝 {data['text']}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_"))
async def hide_message(callback: CallbackQuery):
    """Удаляет аудиосообщение с переводом."""
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if data and data.get("audio_message_id"):
        await callback.bot.delete_message(
            chat_id=callback.message.chat.id,
            message_id=data["audio_message_id"]
        )
        # Сбрасываем ID, чтобы не пытаться редактировать удалённое
        data["audio_message_id"] = None
        last_bot_response[user_id] = data
    await callback.answer()

@router.message(F.text)
async def text_fallback(message: Message):
    """Напоминает пользователю использовать голосовые сообщения."""
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") == "speaking_active":
        await message.answer(
            "📝 Please use voice messages so I can help with pronunciation 🎤\n"
            "Just tap the microphone and speak in English."
        )
    else:
        await message.answer("Press '🎤 Speaking' button to start a voice lesson.")