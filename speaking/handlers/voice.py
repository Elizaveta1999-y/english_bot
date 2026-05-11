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
last_bot_response = {}  # user_id -> {"text": eng_text, "message_id": ...}

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

    # Сохраняем историю (уже есть в вашем коде)
    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    # Извлечение имени (как было)
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
                await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'))
                os.unlink(voice_path)
            # Отправляем текст с кнопками
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📄 Текст", callback_data=f"show_text_{user_id}"),
                 InlineKeyboardButton(text="🇷🇺 Перевести", callback_data=f"translate_{user_id}")]
            ])
            await message.answer(response_text, reply_markup=keyboard)
            # Сохраняем в историю
            history.append({"role": "assistant", "text": response_text})
            user_state["history"] = history
            set_user_state(user_id, user_state)
            last_bot_response[user_id] = {"text": response_text, "message_id": None}
            return

    ai_response = await process_voice_message(user_id, user_text)
    voice_path = await text_to_voice(ai_response)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'))
        os.unlink(voice_path)

    # Отправляем текстовую версию ответа с инлайн-кнопками
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Текст", callback_data=f"show_text_{user_id}"),
         InlineKeyboardButton(text="🇷🇺 Перевести", callback_data=f"translate_{user_id}")]
    ])
    sent_msg = await message.answer(ai_response, reply_markup=keyboard)
    
    # Сохраняем ответ и ID сообщения (чтобы потом обновлять кнопки, если нужно)
    last_bot_response[user_id] = {"text": ai_response, "message_id": sent_msg.message_id}
    
    # Сохраняем в историю
    history.append({"role": "assistant", "text": ai_response})
    user_state["history"] = history
    set_user_state(user_id, user_state)

@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if data and data.get("text"):
        await callback.message.answer(f"📄 Текст ответа:\n\n{data['text']}")
    else:
        await callback.message.answer("Нет сохранённого текста. Отправьте новое голосовое сообщение.")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_"))
async def translate_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.message.answer("Нет сообщения для перевода. Отправьте голосовое.")
        await callback.answer()
        return
    translation = chat(f"Translate the following English text to Russian. Output only the translation, no extras.\n\n{data['text']}", max_tokens=500, temperature=0.3)
    await callback.message.answer(f"🇷🇺 Перевод:\n\n{translation}")
    await callback.answer()

# Обработка текстовых сообщений вне режима (как было)
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