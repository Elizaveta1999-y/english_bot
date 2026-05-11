import os
import re
import asyncio
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

router = Router()
# Храним последние ответы для каждого пользователя (оригинал и перевод)
last_bot_response = {}  # {user_id: {"text": str, "translation": str}}

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())

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

    # Извлечение имени
    name_match = re.search(r"(?:my name is|i am|i'm|call me)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
    if name_match:
        name = name_match.group(1)
        set_user_name(user_id, name)
        user_text = re.sub(r"(?:my name is|i am|i'm|call me)\s+[A-Za-z]+", "", user_text, flags=re.IGNORECASE).strip()
        if not user_text:
            response_text = f"Nice to meet you, {name}! Tell me something about yourself."
            voice_path = await text_to_voice(response_text)
            if voice_path:
                with open(voice_path, 'rb') as f:
                    audio_bytes = f.read()
                # Кнопка "Текст" для этого голосового
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_original_{user_id}")]
                ])
                await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'), reply_markup=keyboard)
                os.unlink(voice_path)
            history.append({"role": "assistant", "text": response_text})
            user_state["history"] = history
            set_user_state(user_id, user_state)
            # Сохраняем ответ для кнопок
            last_bot_response[user_id] = {"text": response_text, "translation": None}
            return

    ai_response = await process_voice_message(user_id, user_text)
    voice_path = await text_to_voice(ai_response)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        # Отправляем голосовое с inline-кнопкой "Текст"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_original_{user_id}")]
        ])
        await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'), reply_markup=keyboard)
        os.unlink(voice_path)

    history.append({"role": "assistant", "text": ai_response})
    user_state["history"] = history
    set_user_state(user_id, user_state)
    last_bot_response[user_id] = {"text": ai_response, "translation": None}

# Обработчик кнопки "Текст"
@router.callback_query(lambda c: c.data.startswith("show_original_"))
async def show_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста для отображения.", show_alert=True)
        return
    original = data["text"]
    # Отправляем оригинальный текст с кнопкой "Перевести"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}")]
    ])
    await callback.message.answer(f"📝 Оригинал (англ.):\n\n{original}", reply_markup=keyboard)
    await callback.answer()

# Обработчик кнопки "Перевести"
@router.callback_query(lambda c: c.data.startswith("translate_"))
async def translate_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста для перевода.", show_alert=True)
        return
    # Если перевод уже есть в кэше, используем его
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(f"Translate the following English text to Russian. Output only the translation, no extras.\n\n{data['text']}", max_tokens=300, temperature=0.3)
        data["translation"] = translation
        last_bot_response[user_id] = data
    await callback.message.answer(f"🇷🇺 Перевод:\n\n{translation}")
    await callback.answer()

# Обработка текстовых сообщений (вне режима или просьба использовать голос)
@router.message(F.text)
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") == "speaking_active":
        await message.answer(
            "📝 Пожалуйста, используйте голосовые сообщения, чтобы я мог помочь с произношением 🎤\n"
            "Просто нажмите на значок микрофона и говорите по-английски."
        )
    else:
        await message.answer("Нажмите кнопку '🎤 Speaking', чтобы начать голосовой урок.")