import os
import re
import asyncio
import logging
import subprocess
import tempfile
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message, process_roleplay_message, generate_roleplay_feedback
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

logger = logging.getLogger(__name__)
router = Router()
last_bot_response = {}
last_text_response = {}

def convert_to_opus(mp3_path: str) -> str:
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

    mode = user_state.get("mode")
    if mode == "roleplay_active":
        ai_response = await process_roleplay_message(user_id, user_text)
    else:
        if mode != "speaking_active":
            set_user_mode(user_id, "speaking_active")
            set_user_state(user_id, user_state)
        ai_response = await process_voice_message(user_id, user_text)

    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    await _send_voice_message(message, ai_response, user_id)

async def _send_voice_message(message: Message, text: str, user_id: int):
    await message.bot.send_chat_action(chat_id=message.chat.id, action="record_voice")
    mp3_path = await text_to_voice(text)
    if not mp3_path:
        await _send_text_message_with_buttons(message, text, user_id)
        return

    ogg_path = convert_to_opus(mp3_path)
    with open(ogg_path, 'rb') as f:
        audio_bytes = f.read()
    os.unlink(mp3_path)
    os.unlink(ogg_path)

    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
    ])
    sent = await message.answer_audio(
        BufferedInputFile(audio_bytes, filename='voice.ogg'),
        caption="",
        reply_markup=inline_keyboard
    )
    last_bot_response[user_id] = {
        "text": text,
        "translation": None,
        "audio_message_id": sent.message_id
    }

async def _send_text_message_with_buttons(message: Message, text: str, user_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    sent = await message.answer(text, reply_markup=keyboard)
    last_text_response[user_id] = {
        "text": text,
        "translation": None,
        "message_id": sent.message_id
    }

# ========== ОБРАБОТЧИКИ ТЕКСТОВЫХ СООБЩЕНИЙ (СНАЧАЛА КНОПКИ) ==========
@router.message(F.text == "💡 Что ответить?")
async def hint_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    topic = user_state.get("roleplay_topic")
    history = user_state.get("history", [])
    if not topic:
        await message.answer("Эта кнопка доступна только в режиме ролевой игры.")
        return
    context = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-5:]])
    prompt = f"""Ты – участник ролевой игры (тема: {topic}). Пользователь не знает, что ответить. Дай 2–3 коротких варианта ответа (по-английски), подходящих по контексту. Контекст диалога:
{context}

Ответь только вариантами (без номеров, просто строки)."""
    hints = chat(prompt, max_tokens=200, temperature=0.7)
    await message.answer(f"💡 <b>Варианты ответа</b>:\n{hints}", parse_mode="HTML")

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    if user_id in last_bot_response:
        del last_bot_response[user_id]
    if user_id in last_text_response:
        del last_text_response[user_id]
    await message.answer(
        "🔚 Режим завершён. Чтобы начать снова, нажмите /start и выберите Speaking или RolePlay.",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "roleplay_active":
        await message.answer("Эта кнопка доступна только в ролевой игре.")
        return
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("Диалог ещё не начался. Сначала отправьте несколько сообщений.")
        return
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    conversation = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-20:]])
    topic = user_state.get("roleplay_topic", "ролевая игра")
    category = user_state.get("roleplay_category", "custom")
    if category == "custom":
        custom_scenario = user_state.get("custom_scenario", "")
        feedback = await generate_roleplay_feedback(conversation, topic, custom_scenario=custom_scenario)
    else:
        feedback = await generate_roleplay_feedback(conversation, topic)
    await message.answer(f"📊 <b>Анализ диалога</b>\n\n{feedback}", parse_mode="HTML")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Продолжить диалог", callback_data="continue_roleplay")],
        [InlineKeyboardButton(text="🏠 Выйти в меню", callback_data="exit_to_menu")]
    ])
    await message.answer("Желаете продолжить ролевую игру или завершить?", reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "continue_roleplay")
async def continue_roleplay(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Продолжаем. Отправляйте следующие сообщения.")

@router.callback_query(lambda c: c.data == "exit_to_menu")
async def exit_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    if user_id in last_bot_response:
        del last_bot_response[user_id]
    if user_id in last_text_response:
        del last_text_response[user_id]
    await callback.message.answer(
        "🔚 Режим завершён. Чтобы начать снова, нажмите /start и выберите Speaking или RolePlay.",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()

@router.message(F.text == "📊 Я всё! Фидбек")
async def feedback_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        await message.answer("Фидбек доступен только в режиме Speaking (без ролевой игры).")
        return
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("Вы ещё не общались. Отправьте несколько голосовых сообщений.")
        return
    conversation = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    prompt = f"""Ты опытный учитель английского. Дай короткий фидбек на русском языке.
Диалог:
{conversation}
Формат:
<b>📝 Ошибки и исправления</b> (2-3 пункта, кратко)
<b>💡 Рекомендации</b> (2 фразы)
<b>📚 Словарик</b> (5 слов/фраз: слово — перевод (пример))"""
    feedback = chat(prompt, max_tokens=600, temperature=0.5)
    await message.answer(f"📊 <b>Ваш фидбек</b>:\n\n{feedback}", parse_mode="HTML")

# ========== ОБЩИЙ ОБРАБОТЧИК ДЛЯ ПРОЧИХ ТЕКСТОВЫХ СООБЩЕНИЙ (ДОЛЖЕН БЫТЬ ПОСЛЕДНИМ) ==========
@router.message(F.text)
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    if mode in ("speaking_active", "roleplay_active"):
        user_text = message.text
        if mode == "roleplay_active":
            ai_response = await process_roleplay_message(user_id, user_text)
            await _send_text_message_with_buttons(message, ai_response, user_id)
        else:
            ai_response = await process_voice_message(user_id, user_text)
            await _send_voice_message(message, ai_response, user_id)
        history = user_state.get("history", [])
        history.append({"role": "user", "text": user_text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)
    else:
        await message.answer("Нажмите /start и выберите Speaking или RolePlay, чтобы начать общение.")

# ========== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (INLINE КНОПКИ ДЛЯ ПЕРЕВОДА) ==========
# (они уже были, но для краткости я их не копирую, в реальном файле они должны быть)