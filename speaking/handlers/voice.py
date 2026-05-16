import os
import re
import asyncio
import logging
import subprocess
import tempfile
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

logger = logging.getLogger(__name__)
router = Router()
last_bot_response = {}

def convert_to_opus(mp3_path: str) -> str:
    """Конвертирует MP3 в OGG (кодек OPUS) для правильного отображения Telegram как голосового сообщения."""
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = [
        "ffmpeg", "-i", mp3_path,
        "-c:a", "libopus", "-ar", "16000", "-ac", "1",
        "-b:a", "16k", ogg_path, "-y"
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return ogg_path

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    logger.info(f"Received voice from user {user_id}")
    user_state = get_user_state(user_id)

    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())
    logger.info(f"Recognized text: {user_text}")

    if not user_text:
        await message.answer("Sorry, I didn't catch that. Could you repeat?")
        return

    if user_state.get("mode") != "speaking_active":
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)

    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    name_match = re.search(r"(?:my name is|i am|i'm|call me)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
    if name_match:
        name = name_match.group(1)
        set_user_name(user_id, name)
        user_text = re.sub(r"(?:my name is|i am|i'm|call me)\s+[A-Za-z]+", "", user_text, flags=re.IGNORECASE).strip()
        if not user_text:
            response_text = f"Nice to meet you, {name}! Tell me something about yourself."
            await _send_voice_message(message, response_text, user_id)
            history.append({"role": "assistant", "text": response_text})
            user_state["history"] = history
            set_user_state(user_id, user_state)
            return

    ai_response = await process_voice_message(user_id, user_text)
    logger.info(f"AI response: {ai_response[:100]}...")
    await _send_voice_message(message, ai_response, user_id)

    history.append({"role": "assistant", "text": ai_response})
    user_state["history"] = history
    set_user_state(user_id, user_state)

async def _send_voice_message(message: Message, text: str, user_id: int):
    """Генерирует аудио (OGG OPUS) и отправляет как голосовое сообщение с подписью и кнопкой."""
    # Показываем индикатор "записывает голосовое сообщение"
    await message.bot.send_chat_action(chat_id=message.chat.id, action="record_voice")

    mp3_path = await text_to_voice(text)
    if not mp3_path:
        await message.answer(text)
        return

    ogg_path = convert_to_opus(mp3_path)
    with open(ogg_path, 'rb') as f:
        audio_bytes = f.read()
    os.unlink(mp3_path)
    os.unlink(ogg_path)

    # Кнопка "Текст" (показывает оригинал)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
    ])

    # ⬇️ Изменение здесь: отправляем как голосовое сообщение с caption
    sent = await message.answer_voice(
        BufferedInputFile(audio_bytes, filename='voice.ogg'),
        caption="",  # Отправляем с пустой подписью, которую потом будем менять
        reply_markup=keyboard
    )
    last_bot_response[user_id] = {
        "text": text,
        "translation": None,
        "voice_message_id": sent.message_id  # Сохраняем ID сообщения
    }

# --- Обработчики inline-кнопок (без изменений) ---
@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No text available.", show_alert=True)
        return

    original = data["text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["voice_message_id"],
        caption=f"📝 {original}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_"))
async def translate_caption(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No text to translate.", show_alert=True)
        return

    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(
            f"Translate the following English text to Russian. Output only the translation, no extras.\n\n{data['text']}",
            max_tokens=300, temperature=0.3
        )
        data["translation"] = translation
        last_bot_response[user_id] = data

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["voice_message_id"],
        caption=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_"))
async def revert_to_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No original text.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["voice_message_id"],
        caption=f"📝 {data['text']}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_"))
async def hide_message(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("voice_message_id"):
        await callback.answer("No message to hide.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["voice_message_id"],
        caption="",
        reply_markup=keyboard
    )
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

@router.message(F.text)
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") == "speaking_active":
        await message.answer(
            "📝 Please use voice messages so I can help with pronunciation 🎤\n"
            "Just tap the microphone and speak in English."
        )
    else:
        await message.answer("Press '🎤 Speaking' button to start a voice lesson.")