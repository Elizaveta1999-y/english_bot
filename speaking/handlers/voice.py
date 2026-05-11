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
# Хранилище: {user_id: {"text": str, "translation": str, "text_message_id": int}}
last_bot_response = {}

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    logger.info(f"Received voice from user {user_id}")
    user_state = get_user_state(user_id)

    # 1. Скачиваем и распознаём
    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())
    logger.info(f"Recognized text: {user_text}")

    if not user_text:
        await message.answer("Sorry, I didn't catch that. Could you repeat?")
        return

    # 2. Активируем режим speaking, если ещё не активен
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

    # 4. Извлечение имени (опционально)
    name_match = re.search(r"(?:my name is|i am|i'm|call me)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
    if name_match:
        name = name_match.group(1)
        set_user_name(user_id, name)
        user_text = re.sub(r"(?:my name is|i am|i'm|call me)\s+[A-Za-z]+", "", user_text, flags=re.IGNORECASE).strip()
        if not user_text:
            response_text = f"Nice to meet you, {name}! Tell me something about yourself."
            await _send_voice_reply(message, response_text, user_id)
            history.append({"role": "assistant", "text": response_text})
            user_state["history"] = history
            set_user_state(user_id, user_state)
            last_bot_response[user_id] = {"text": response_text, "translation": None, "text_message_id": None}
            return

    # 5. Генерируем ответ через DeepSeek
    ai_response = await process_voice_message(user_id, user_text)
    logger.info(f"AI response: {ai_response[:100]}...")
    await _send_voice_reply(message, ai_response, user_id)

    # 6. Сохраняем ответ в историю и в last_bot_response
    history.append({"role": "assistant", "text": ai_response})
    user_state["history"] = history
    set_user_state(user_id, user_state)
    last_bot_response[user_id] = {"text": ai_response, "translation": None, "text_message_id": None}

async def _send_voice_reply(message: Message, text: str, user_id: int):
    """Вспомогательная функция: генерирует голос и отправляет с кнопкой 'Текст'."""
    voice_path = await text_to_voice(text)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_original_{user_id}")]
        ])
        await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'), reply_markup=keyboard)
        os.unlink(voice_path)
    else:
        # Fallback: отправить текст, если голос не сгенерировался
        await message.answer(text)

@router.callback_query(lambda c: c.data.startswith("show_original_"))
async def show_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No text available.", show_alert=True)
        return

    original = data["text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}")]
    ])
    # Отправляем новое текстовое сообщение с оригиналом и кнопкой "Перевести"
    msg = await callback.message.answer(
        f"📝 Original (English):\n\n{original}",
        reply_markup=keyboard
    )
    data["text_message_id"] = msg.message_id
    last_bot_response[user_id] = data
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_"))
async def translate_text(callback: CallbackQuery):
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

    # Клавиатура с двумя кнопками: скрыть перевод (вернуть оригинал) и показать оригинал (то же самое, что скрыть)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Скрыть перевод", callback_data=f"hide_translation_{user_id}"),
            InlineKeyboardButton(text="📜 Оригинал", callback_data=f"show_only_original_{user_id}")
        ]
    ])
    new_text = f"📝 Original (English):\n\n{data['text']}\n\n🇷🇺 Translation:\n\n{translation}"
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["text_message_id"],
        text=new_text,
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_translation_"))
async def hide_translation(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No data.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}")]
    ])
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["text_message_id"],
        text=f"📝 Original (English):\n\n{data['text']}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("show_only_original_"))
async def show_only_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[3])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No data.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}")]
    ])
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["text_message_id"],
        text=f"📝 Original (English):\n\n{data['text']}",
        reply_markup=keyboard
    )
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