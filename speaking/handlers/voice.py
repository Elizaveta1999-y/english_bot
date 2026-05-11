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
            voice_path = await text_to_voice(response_text)
            if voice_path:
                with open(voice_path, 'rb') as f:
                    audio_bytes = f.read()
                await message.answer_voice(BufferedInputFile(audio_bytes, filename='response.mp3'))
                os.unlink(voice_path)
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
        await message.answer("Вы ещё не общались. Отправьте несколько голосовых сообщений.")
        return

    conversation = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h.get('text', h.get('content', ''))}" for h in history[-10:]])
    
    prompt = f"""You are an experienced American English teacher. Analyze the following conversation and provide feedback **in Russian language**.

Conversation:
{conversation}

Please provide a response in Russian, following this format (text only, no voice):

1. **Ошибки и исправления**: Перечислите основные грамматические/лексические ошибки ученика. Для каждой ошибки дайте исправление и краткое правило.

2. **Рекомендации по улучшению**: Предложите 2-3 практических совета для улучшения произношения, беглости или грамматики.

3. **Словарик для изучения**: Выберите 5-8 полезных слов/фраз из диалога. Для каждого дайте:
   - Оригинал (английский)
   - Перевод на русский
   - Пример предложения (из диалога или новый)

Пишите дружелюбно, поддерживающе. Будьте краткими, но полезными."""

    feedback = chat(prompt, max_tokens=1200, temperature=0.5)
    await message.answer(f"📊 Ваш фидбек:\n\n{feedback}")

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