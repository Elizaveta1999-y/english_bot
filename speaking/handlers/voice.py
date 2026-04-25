from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import add_to_history, get_user_history
import tempfile
import os

router = Router()

# Хранилище последних ответов бота для каждого пользователя (чтобы показывать перевод/оригинал)
last_bot_responses = {}

def get_translate_keyboard(user_id: str, original_text: str) -> InlineKeyboardMarkup:
    """Создаёт кнопки для перевода и озвучки"""
    # Для простоты кнопки вызывают callback с данными
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Перевод", callback_data=f"translate_{user_id}"),
            InlineKeyboardButton(text="🇬🇧 Оригинал", callback_data=f"original_{user_id}")
        ],
        [
            InlineKeyboardButton(text="🔊 Озвучить", callback_data=f"speak_{user_id}")
        ]
    ])
    return keyboard

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    try:
        # 1. Скачиваем голосовое сообщение
        file = await message.bot.get_file(message.voice.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        
        # 2. Распознаём речь (теперь через Google)
        user_text = await voice_to_text(file_bytes.read())
        if not user_text:
            await message.answer("❌ Не удалось распознать речь. Попробуйте говорить чётче.")
            return
        
        # 3. Получаем ответ от DeepSeek с исправлениями
        ai_answer = await process_voice_message(user_id, user_text)
        
        # 4. Сохраняем последний ответ бота (чтобы потом перевести)
        last_bot_responses[user_id] = {
            "original": ai_answer,
            "user_text": user_text
        }
        
        # 5. Отправляем текст + кнопки
        keyboard = get_translate_keyboard(user_id, ai_answer)
        await message.answer(
            f"🗣 You said: {user_text}\n\n🤖 Teacher:\n{ai_answer}",
            reply_markup=keyboard
        )
        
        # НЕ генерируем голос автоматически (экономия)
        
    except Exception as e:
        print("VOICE ERROR:", e)
        await message.answer("⚠️ Something went wrong. Please try again.")

# Обработчик кнопки "Перевод"
@router.callback_query(lambda c: c.data.startswith("translate_"))
async def translate_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    if user_id in last_bot_responses:
        original_answer = last_bot_responses[user_id]["original"]
        # Здесь можно вызвать DeepSeek для перевода на русский (экономия: просто отправляем ссылку на перевод?)
        # Для простоты пока отправим заглушку. В будущем можно сделать реальный перевод через DeepSeek.
        await callback.message.answer("🇷🇺 Перевод: (функция в разработке, скоро будет)")
    else:
        await callback.message.answer("Нет активного сообщения для перевода")
    await callback.answer()

# Обработчик кнопки "Оригинал"
@router.callback_query(lambda c: c.data.startswith("original_"))
async def original_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    if user_id in last_bot_responses:
        original = last_bot_responses[user_id]["original"]
        await callback.message.answer(f"🇬🇧 Оригинал:\n{original}")
    else:
        await callback.message.answer("Нет сохранённого оригинала")
    await callback.answer()

# Обработчик кнопки "Озвучить" (генерируем голос только по запросу)
@router.callback_query(lambda c: c.data.startswith("speak_"))
async def speak_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    if user_id in last_bot_responses:
        text_to_speak = last_bot_responses[user_id]["original"]
        # Генерируем голос через ElevenLabs
        audio_bytes = await text_to_voice(text_to_speak)
        if audio_bytes:
            # Сохраняем во временный файл и отправляем как голосовое
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            # Отправляем
            voice_file = FSInputFile(tmp_path)
            await callback.message.answer_voice(voice_file)
            # Удаляем временный файл
            os.unlink(tmp_path)
        else:
            await callback.message.answer("Не удалось сгенерировать голос")
    else:
        await callback.message.answer("Нет текста для озвучки")
    await callback.answer()