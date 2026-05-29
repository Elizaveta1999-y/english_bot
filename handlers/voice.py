import os
import tempfile
import subprocess
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message, process_roleplay_message
from speaking.services.tts import text_to_voice
from data.users import get_user_state, set_user_state, set_user_mode, add_to_history

router = Router()
last_bot_response = {}

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

# Сюда нужно добавить обработчики show_text_, translate_, original_, hide_
# (они остаются без изменений, я не привожу их для краткости, но вы можете скопировать из вашего старого app.py)
# ========== ПЕРЕВОД И Т.Д. ==========
@dp.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста.", show_alert=True)
        return
    original = data["text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"), InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption=f"📝 {original}", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("translate_") and not c.data.startswith("translate_text_"))
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_{user_id}"), InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption=f"🇷🇺 {translation}", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("original_") and not c.data.startswith("original_text_"))
async def revert_to_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"), InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption=f"📝 {data['text']}", reply_markup=keyboard)
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("hide_") and not c.data.startswith("hide_text_"))
async def hide_message(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("audio_message_id"):
        await callback.answer("Нет сообщения.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]])
    await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=data["audio_message_id"], caption="", reply_markup=keyboard)
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("translate_text_"))
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_text_{user_id}")]])
    await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=data["message_id"], text=f"🇷🇺 {translation}", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("original_text_"))
async def original_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]])
    await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=data["message_id"], text=data["text"], reply_markup=keyboard)
    data["translation"] = None
    last_text_response[user_id] = data
    await callback.answer()

# ========== ОБЩИЙ ОБРАБОТЧИК ТЕКСТА ==========
@dp.message(F.text)
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("awaiting_custom_scenario"):
        return
    mode = user_state.get("mode")
    if mode in ("speaking_active", "roleplay_active"):
        if not is_user_message_countable(message.text):
            return
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        if mode == "roleplay_active":
            ai_response = await process_roleplay_message(user_id, message.text)
        else:
            ai_response = await process_voice_message(user_id, message.text)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]])
        sent = await message.answer(ai_response, reply_markup=keyboard)
        last_text_response[user_id] = {"text": ai_response, "translation": None, "message_id": sent.message_id}
        history = user_state.get("history", [])
        history.append({"role": "user", "text": message.text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)
    else:
        await message.answer("Нажмите /start и выберите Speaking или RolePlay.")

# ========== ВЕБХУК ==========
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"

async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(text="Error", status=500)

async def health(request):
    return web.Response(text="Bot is running", status=200)

web_app = web.Application()
web_app.router.add_post(WEBHOOK_PATH, handle_webhook)
web_app.router.add_get("/", health)

async def on_startup(web_app):
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set to {webhook_url}")

web_app.on_startup.append(on_startup)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    web.run_app(web_app, host='0.0.0.0', port=port)