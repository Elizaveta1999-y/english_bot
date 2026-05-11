import os
import re
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

router = Router()

# Словарь для хранения последнего ответа бота (текст) для каждого пользователя
last_bot_response = {}

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
                last_bot_response[user_id] = response_text
            return

    ai_response = await process_voice_message(user_id, user_text)
    voice_path = await text_to_voice(ai_response)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'))
        os.unlink(voice_path)
        last_bot_response[user_id] = ai_response

# --- Обработчики кнопок перевода ---
@router.message(F.text == "🇷🇺 Перевод")
async def translate_message(message: Message):
    user_id = message.from_user.id
    original = last_bot_response.get(user_id)
    if not original:
        await message.answer("Нет сохранённого сообщения для перевода. Сначала пообщайтесь с ботом.")
        return
    # Вызываем DeepSeek для перевода на русский
    translation = chat(f"Translate the following English text to Russian. Output ONLY the translation, no extra text:\n\n{original}", max_tokens=500, temperature=0.3)
    await message.answer(f"🇷🇺 Перевод:\n\n{translation}")

@router.message(F.text == "🇺🇸 Original")
async def original_message(message: Message):
    user_id = message.from_user.id
    original = last_bot_response.get(user_id)
    if not original:
        await message.answer("No saved message. Please talk to the bot first.")
        return
    await message.answer(f"🇺🇸 Original (American English):\n\n{original}")

# (Исправление для русскоязычной кнопки, если название другое)
# Если используете "🇷🇺 Translate", измените соответственно.

@router.message(F.text)
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") == "speaking_active":
        await message.answer(
            "📝 Please use voice messages so I can help with pronunciation 🎤\n"
            "Just tap the microphone and speak in American English."
        )
    else:
        await message.answer("Press the '🎤 Speaking' button to start.")