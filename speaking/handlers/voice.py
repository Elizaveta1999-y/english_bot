from aiogram import Router, F
from aiogram.types import Message
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice

router = Router()


@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id

    # 📥 получаем файл
    file = await message.bot.get_file(message.voice.file_id)

    # 🔗 получаем ссылку
    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"

    print("VOICE FILE URL:", file_url)

    # 🤖 отправляем в AI
    ai_text = await process_voice_message(
        audio_url=file_url,
        mode="speaking",
        user_name="User"
    )

    print("AI TEXT:", ai_text)

    # 🔊 озвучка
    voice = await text_to_voice(ai_text)

    await message.answer_voice(voice)