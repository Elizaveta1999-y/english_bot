import os
import tempfile
import subprocess
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message, process_roleplay_message
from speaking.services.tts import text_to_voice
from data.users import get_user_state, set_user_state, set_user_mode, add_to_history
from services.deepseek import chat

router = Router()
last_bot_response = {}
last_text_response = {}

def convert_to_opus(mp3_path: str) -> str:
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", "-ar", "16000", "-ac", "1", "-b:a", "16k", ogg_path, "-y"]
    subprocess.run(cmd, check=True, capture_output=True)
    return ogg_path

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())
    if not user_text:
        await message.answer("Не понял, повторите.")
        return
    mode = user_state.get("mode")
    if mode == "roleplay_active":
        ai_response = await process_roleplay_message(user_id, user_text)
    else:
        if mode != "speaking_active":
            set_user_mode(user_id, "speaking_active")
        ai_response = await process_voice_message(user_id, user_text)
    if user_text.strip():
        history = user_state.get("history", [])
        history.append({"role": "user", "text": user_text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)
    await message.bot.send_chat_action(chat_id=message.chat.id, action="record_voice")
    voice_path = await text_to_voice(ai_response)
    if voice_path:
        ogg_path = convert_to_opus(voice_path)
        with open(ogg_path, 'rb') as f:
            audio_bytes = f.read()
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
        ])
        sent = await message.answer_audio(BufferedInputFile(audio_bytes, filename='voice.ogg'), caption="", reply_markup=inline_keyboard)
        last_bot_response[user_id] = {"text": ai_response, "translation": None, "audio_message_id": sent.message_id}
        os.unlink(voice_path)
        os.unlink(ogg_path)
    else:
        await message.answer(ai_response)

# ---------- ОБРАБОТЧИКИ КНОПОК ПОД ГОЛОСОВЫМИ (с использованием router) ----------
@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста.", show_alert=True)
        return
    original = data["text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
         InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]
    ])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption=f"📝 {original}", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_") and not c.data.startswith("translate_text_"))
async def translate_caption(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста.", show_alert=True)
        return
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(f"Translate to Russian. Output ONLY translation:\n\n{data['text']}", max_tokens=300, temperature=0.3)
        translation = translation.strip('*"\'')
        data["translation"] = translation
        last_bot_response[user_id] = data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_{user_id}"),
         InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]
    ])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption=f"🇷🇺 {translation}", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_") and not c.data.startswith("original_text_"))
async def revert_to_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
         InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]
    ])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption=f"📝 {data['text']}", reply_markup=keyboard)
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_") and not c.data.startswith("hide_text_"))
async def hide_message(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("audio_message_id"):
        await callback.answer("Нет сообщения.", show_alert=True)
        return
    # Очищаем caption, но не удаляем сообщение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
    ])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption="", reply_markup=keyboard)
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

# ---------- ОБРАБОТЧИКИ ТЕКСТОВОГО ПЕРЕВОДА ----------
@router.callback_query(lambda c: c.data.startswith("translate_text_"))
async def translate_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста для перевода.", show_alert=True)
        return
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(f"Translate to Russian. Output ONLY translation:\n\n{data['text']}", max_tokens=300, temperature=0.3)
        translation = translation.strip('*"\'')
        data["translation"] = translation
        last_text_response[user_id] = data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_text_{user_id}")]
    ])
    await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=data["message_id"], text=f"🇷🇺 {translation}", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_text_"))
async def original_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=data["message_id"], text=data["text"], reply_markup=keyboard)
    data["translation"] = None
    last_text_response[user_id] = data
    await callback.answer()