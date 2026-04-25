from aiogram import Router, F
from aiogram.types import Message
import tempfile
import os
import asyncio
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, set_user_name, set_user_level, add_to_history, get_user_state

router = Router()

# Хранилище для временного хранения данных пользователя между шагами
temp_user_data = {}

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    # --- ШАГ 1: Определяем, на каком этапе диалога находится пользователь ---

    # 1. Ожидание имени
    if user_state.get("waiting_for_name"):
        user_text = await voice_to_text(await message.bot.download_file((await message.bot.get_file(message.voice.file_id)).file_path))
        if user_text:
            set_user_name(user_id, user_text.strip())
            user_state["waiting_for_name"] = False
            await message.answer("👋")
            # Голосовое предложение выбрать тему
            voice_response = "Nice to meet you! Please choose a topic: travel, hobbies, or family?"
            voice_file = await text_to_voice(voice_response)
            if voice_file:
                await message.answer_voice(voice_file)

    # 2. Ожидание темы
    elif user_state.get("waiting_for_topic"):
        user_text = await voice_to_text(await message.bot.download_file((await message.bot.get_file(message.voice.file_id)).file_path))
        if user_text and user_text.lower() in ["travel", "hobbies", "family"]:
            user_state["waiting_for_topic"] = False
            set_user_mode(user_id, "speaking_active")
            # Голосовое начало разговора по теме
            voice_response = f"Great choice! Let's talk about {user_text}. Where do you like to go on vacation?"
            voice_file = await text_to_voice(voice_response)
            if voice_file:
                await message.answer_voice(voice_file)
        else:
            # Голосовое уточнение
            voice_response = "Sorry, I didn't catch that. Please choose: travel, hobbies, or family?"
            voice_file = await text_to_voice(voice_response)
            if voice_file:
                await message.answer_voice(voice_file)

    # 3. Активный диалог
    elif user_state.get("mode") == "speaking_active":
        try:
            # Получаем файл
            file = await message.bot.get_file(message.voice.file_id)
            file_bytes = await message.bot.download_file(file.file_path)

            # Распознаем речь
            user_text = await voice_to_text(file_bytes.read())
            if not user_text:
                # Сообщение об ошибке распознавания - голосом
                voice_response = "I'm having trouble understanding. Could you say that again, please?"
                voice_file = await text_to_voice(voice_response)
                if voice_file:
                    await message.answer_voice(voice_file)
                return

            # Получаем ответ от AI
            ai_response_text = await process_voice_message(user_id, user_text)

            # Генерируем голос
            voice_file = await text_to_voice(ai_response_text)

            if voice_file:
                await message.answer_voice(voice_file)
            else:
                # Если не удалось сгенерировать голос, отправляем текст (но по ТЗ так быть не должно)
                await message.answer(ai_response_text)

        except Exception as e:
            print("VOICE HANDLER ERROR:", e)
            voice_response = "Sorry, something went wrong. Let's try again!"
            voice_file = await text_to_voice(voice_response)
            if voice_file:
                await message.answer_voice(voice_file)