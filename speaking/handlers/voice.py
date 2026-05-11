import os
import re
import asyncio
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

router = Router()
last_bot_response = {}  # для кнопок перевода

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

    # Сохраняем сообщение пользователя в историю
    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    # Ограничим историю 20 последними сообщениями
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    # Извлечение имени (если есть)
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
            # Сохраним ответ бота в историю
            history.append({"role": "assistant", "text": response_text})
            user_state["history"] = history
            set_user_state(user_id, user_state)
            return

    ai_response = await process_voice_message(user_id, user_text)
    voice_path = await text_to_voice(ai_response)
    if voice_path:
        with open(voice_path, 'rb') as f:
            audio_bytes = f.read()
        await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'))
        os.unlink(voice_path)

    # Сохраняем ответ бота в историю и для перевода
    history.append({"role": "assistant", "text": ai_response})
    user_state["history"] = history
    set_user_state(user_id, user_state)
    last_bot_response[user_id] = {"text": ai_response, "timestamp": asyncio.get_event_loop().time()}

@router.message(F.text == "🇺🇸 Original")
async def show_original(message: Message):
    user_id = message.from_user.id
    data = last_bot_response.get(user_id)
    if data and data.get("text"):
        await message.answer(f"🇺🇸 Original:\n\n{data['text']}")
    else:
        await message.answer("No message to show. Send a voice message first.")

@router.message(F.text == "🇷🇺 Перевод")
async def translate_last(message: Message):
    user_id = message.from_user.id
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await message.answer("No message to translate. Send a voice message first.")
        return
    translation = chat(f"Translate the following English text to Russian. Output only the translation, no extras.\n\n{data['text']}", max_tokens=300, temperature=0.3)
    await message.answer(f"🇷🇺 Перевод:\n\n{translation}")

@router.message(F.text == "📊 Я всё! Фидбек")
async def send_feedback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("You haven't had a conversation yet. Send some voice messages first.")
        return

    # Формируем историю диалога для анализа
    conversation = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    prompt = f"""You are an experienced American English teacher. Analyze the following conversation and provide feedback.

Conversation:
{conversation}

Please provide a response in the following format (text only, no voice):

1. **Mistakes & Corrections**: List the main grammar/vocabulary mistakes made by the student. For each, give a correction and a simple rule.

2. **Recommendations for Improvement**: Suggest 2-3 practical tips to improve pronunciation, fluency, or grammar.

3. **Vocabulary Builder**: Extract 5-8 useful words/phrases from the conversation. For each, give:
   - Original word/phrase (English)
   - Translation to Russian
   - Example sentence from the conversation or a new example.

Write in a friendly, encouraging tone. Keep it concise but helpful."""

    feedback = chat(prompt, max_tokens=1200, temperature=0.5)
    await message.answer(f"📊 Feedback for you:\n\n{feedback}")

# Обработка других текстовых сообщений (если пользователь пишет вне режима или ошибка)
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
        await message.answer("Press the '🎤 Speaking' button to start a voice lesson.")