import os
import re
import asyncio
import logging
import subprocess
import tempfile
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message, process_roleplay_message
from speaking.services.tts import text_to_voice
from data.users import set_user_mode, get_user_state, set_user_state, set_user_name
from services.deepseek import chat

logger = logging.getLogger(__name__)
router = Router()
last_bot_response = {}           # для голосовых сообщений (audio)
last_text_response = {}          # для текстовых сообщений в ролевом режиме
# структура: {user_id: {"text": str, "translation": str, "message_id": int}}

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

    # Сохраняем историю
    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    # Отправляем голосовой ответ
    await _send_voice_message(message, ai_response, user_id)

async def _send_voice_message(message: Message, text: str, user_id: int):
    """Отправляет голосовое сообщение с кнопкой 'Текст'."""
    await message.bot.send_chat_action(chat_id=message.chat.id, action="record_voice")

    mp3_path = await text_to_voice(text)
    if not mp3_path:
        # fallback: отправить текстом
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
    """Отправляет текстовое сообщение с кнопкой 'Перевести' (для ролевого режима или fallback)."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    sent = await message.answer(text, reply_markup=keyboard)
    last_text_response[user_id] = {
        "text": text,
        "translation": None,
        "message_id": sent.message_id
    }

# --- Обработчики инлайн-кнопок для голосовых сообщений (без изменений) ---
@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No text available.", show_alert=True)
        return

    original = data["text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"📝 {original}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_"))
async def translate_caption(callback: CallbackQuery):
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_"))
async def revert_to_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No original text.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")
        ]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"📝 {data['text']}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_"))
async def hide_message(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("audio_message_id"):
        await callback.answer("No message to hide.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption="",
        reply_markup=keyboard
    )
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

# --- Обработчики инлайн-кнопок для текстовых сообщений (ролевой режим) ---
@router.callback_query(lambda c: c.data.startswith("translate_text_"))
async def translate_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
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
        last_text_response[user_id] = data

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_text_{user_id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_text_{user_id}")
        ]
    ])
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["message_id"],
        text=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_text_"))
async def original_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("No original text.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["message_id"],
        text=data["text"],
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_text_"))
async def hide_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("message_id"):
        await callback.answer("No message to hide.", show_alert=True)
        return

    await callback.bot.delete_message(
        chat_id=callback.message.chat.id,
        message_id=data["message_id"]
    )
    # Удаляем запись
    del last_text_response[user_id]
    await callback.answer()

# --- Обработчики REPLY-кнопок ---
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

Ответь только вариантами (без номеров, просто строки). Например:
- I'd like to order a coffee.
- Can you recommend a dish?
- What time do you close?"""
    hints = chat(prompt, max_tokens=200, temperature=0.7)
    await message.answer(f"💡 <b>Варианты ответа</b>:\n{hints}", parse_mode="HTML")

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    # Очищаем сохранённые сообщения
    if user_id in last_bot_response:
        del last_bot_response[user_id]
    if user_id in last_text_response:
        del last_text_response[user_id]
    await message.answer(
        "🔚 Режим завершён. Чтобы начать снова, нажмите /start и выберите Speaking или RolePlay.",
        reply_markup=ReplyKeyboardRemove()
    )

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

@router.message(F.text)
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    if mode in ("speaking_active", "roleplay_active"):
        # Пользователь написал текст в активном режиме
        user_text = message.text
        if mode == "roleplay_active":
            ai_response = await process_roleplay_message(user_id, user_text)
            # В ролевом режиме отправляем текстовый ответ с кнопками перевода
            await _send_text_message_with_buttons(message, ai_response, user_id)
        else:
            ai_response = await process_voice_message(user_id, user_text)
            # В speaking режиме можно либо голосом, либо текстом. Отправим голосом, если возможно, иначе текст с кнопками.
            await _send_voice_message(message, ai_response, user_id)
        # Сохраняем историю
        history = user_state.get("history", [])
        history.append({"role": "user", "text": user_text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)
    else:
        await message.answer("Нажмите /start и выберите Speaking или RolePlay, чтобы начать общение.")