import os
import asyncio
import re
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

router = Router()
last_bot_response = {}

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())

    if not user_text:
        await message.answer("Sorry, I couldn't understand. Please try again.")
        return

    # Если ещё не в активном режиме, включаем
    if user_state.get("mode") != "speaking_active":
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)

    # Пытаемся извлечь имя из сообщения, если есть
    name_match = re.search(r"(?:my name is|i am|i'm|call me)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
    if name_match:
        name = name_match.group(1)
        set_user_name(user_id, name)
        # Убираем фразу с именем из текста для AI
        user_text = re.sub(r"(?:my name is|i am|i'm|call me)\s+[A-Za-z]+", "", user_text, flags=re.IGNORECASE).strip()

    # Отправляем запрос в AI
    ai_response = await process_voice_message(user_id, user_text)
    voice_path = await text_to_voice(ai_response)
    if voice_path:
        await message.answer_voice(FSInputFile(voice_path))
        os.unlink(voice_path)
    last_bot_response[user_id] = ai_response

# Обработчики кнопок перевода
@router.message(F.text == "🇷🇺 Перевод")
async def translate_response(message: Message):
    user_id = message.from_user.id
    original = last_bot_response.get(user_id)
    if not original:
        await message.answer("Нет сохранённого ответа для перевода. Сначала поговорите с ботом.")
        return
    translation = chat(f"Translate to Russian. Output ONLY translation:\n\n{original}", max_tokens=500, temperature=0.3)
    await message.answer(f"🇷🇺 Перевод:\n\n{translation}")

@router.message(F.text == "🇬🇧 Оригинал")
async def original_response(message: Message):
    user_id = message.from_user.id
    original = last_bot_response.get(user_id)
    if not original:
        await message.answer("Нет сохранённого ответа.")
        return
    await message.answer(f"🇬🇧 Оригинал:\n\n{original}")