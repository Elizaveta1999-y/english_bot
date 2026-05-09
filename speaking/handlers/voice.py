import os
import asyncio
from aiogram import Router, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_name, set_user_mode, get_user_state, set_user_state
from services.deepseek import chat

router = Router()

# Хранилище последнего ответа для каждого пользователя
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

    # Если ожидаем имя
    if user_state.get("waiting_for_name"):
        import re
        name_match = re.search(r"(?:my name is|i am|i'm|call me)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
        if name_match:
            name = name_match.group(1)
        else:
            name = user_text.strip().split()[0][:20]

        set_user_name(user_id, name)
        user_state["waiting_for_name"] = False
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)

        # Убираем имя из текста, если осталось что-то ещё
        remaining_text = re.sub(r"(?:my name is|i am|i'm|call me)\s+[A-Za-z]+", "", user_text, flags=re.IGNORECASE).strip()
        if remaining_text:
            ai_response = await process_voice_message(user_id, remaining_text)
        else:
            # Если только имя, попросим рассказать тему
            welcome_msg = f"Nice to meet you, {name}! Please tell me something about yourself — your hobby, a book you're reading, or anything you'd like to practice."
            voice_path = await text_to_voice(welcome_msg)
            if voice_path:
                await message.answer_voice(FSInputFile(voice_path))
                os.unlink(voice_path)
            return

        voice_path = await text_to_voice(ai_response)
        if voice_path:
            await message.answer_voice(FSInputFile(voice_path))
            os.unlink(voice_path)
        last_bot_response[user_id] = ai_response
        return

    # Активный диалог
    if user_state.get("mode") == "speaking_active":
        ai_response = await process_voice_message(user_id, user_text)
        voice_path = await text_to_voice(ai_response)
        if voice_path:
            await message.answer_voice(FSInputFile(voice_path))
            os.unlink(voice_path)
        last_bot_response[user_id] = ai_response
    else:
        await message.answer("Please press '🎤 Speaking' button first.")

# --- Обработчики кнопок перевода (из главной клавиатуры) ---
@router.message(F.text == "🇷🇺 Перевод")
async def translate_response(message: Message):
    user_id = message.from_user.id
    original = last_bot_response.get(user_id)
    if not original:
        await message.answer("Нет сохранённого ответа для перевода. Сначала поговорите с ботом через '🎤 Speaking'.")
        return
    translation = chat(f"Translate the following English text to Russian. Output ONLY the translation, no extra text.\n\n{original}", max_tokens=500, temperature=0.3)
    await message.answer(f"🇷🇺 Перевод:\n\n{translation}")

@router.message(F.text == "🇬🇧 Оригинал")
async def original_response(message: Message):
    user_id = message.from_user.id
    original = last_bot_response.get(user_id)
    if not original:
        await message.answer("Нет сохранённого ответа. Сначала поговорите с ботом.")
        return
    await message.answer(f"🇬🇧 Оригинал (англ.):\n\n{original}")