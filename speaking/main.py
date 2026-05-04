import os
import logging
import asyncio
import tempfile
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update, FSInputFile
from aiogram.filters import Command

# Импорты ваших сервисов
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_state, set_user_name, set_user_mode, get_user_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Flask(__name__)

WEBHOOK_PATH = "/webhook"

# ========== ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    await message.answer(
        "Hello! 🤖\n\n"
        "I'm your personal English tutor.\n"
        "Press the button below to start a voice lesson.",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="🎤 Speaking")]],
            resize_keyboard=True
        )
    )

@dp.message(lambda m: m.text == "🎤 Speaking")
async def speaking_mode(message: types.Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"waiting_for_name": True, "mode": "speaking_name"})
    
    await message.answer(
        "🎤 Voice mode activated!\n\n"
        "Please say your name.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    # Голосовое приветствие
    voice_path = await text_to_voice("Hello! I am your voice AI English tutor. What should I call you?")
    if voice_path:
        await message.answer_voice(FSInputFile(voice_path))
        os.unlink(voice_path)

@dp.message(lambda m: m.voice)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    
    # Скачиваем голосовое
    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    
    # Распознаём речь
    user_text = await voice_to_text(file_bytes.read())
    logger.info(f"Recognized: {user_text}")
    
    if not user_text:
        await message.answer("Sorry, I couldn't understand. Please try again.")
        return
    
    # Этап 1: ожидание имени
    if user_state.get("waiting_for_name"):
        name = user_text.strip().split()[0][:20]
        set_user_name(user_id, name)
        user_state["waiting_for_name"] = False
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)
        
        response_text = f"Nice to meet you, {name}! Let's practice English. Just speak naturally. I'll correct your mistakes. Go ahead!"
        voice_path = await text_to_voice(response_text)
        if voice_path:
            await message.answer_voice(FSInputFile(voice_path))
            os.unlink(voice_path)
        return
    
    # Этап 2: активный диалог
    if user_state.get("mode") == "speaking_active":
        ai_response = await process_voice_message(user_id, user_text)
        voice_path = await text_to_voice(ai_response)
        if voice_path:
            await message.answer_voice(FSInputFile(voice_path))
            os.unlink(voice_path)
        else:
            await message.answer(ai_response)

@dp.message()
async def echo(message: types.Message):
    await message.answer(f"Send me a voice message to practice English! 🎤")

# ========== ВЕБХУК ==========

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        update = Update(**data)
        asyncio.run(dp.feed_update(bot, update))
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

@app.route('/')
def index():
    return "Bot is running!", 200

# Установка вебхука
logger.info("Setting webhook...")
external_url = "https://english-bot-d1pd.onrender.com"
webhook_url = f"{external_url}{WEBHOOK_PATH}"

import requests
response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    json={"url": webhook_url, "drop_pending_updates": True}
)
logger.info(f"Webhook response: {response.json()}")