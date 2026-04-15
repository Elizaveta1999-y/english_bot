from aiogram import Router, F
from aiogram.types import Message
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice

router = Router()


@router.message(F.voice)
async def handle_voice(message: Message):
    try:
        # получаем файл
        file = await message.bot.get_file(message.voice.file_id)
        file_path = file.file_path
        file_bytes = await message.bot.download_file(file_path)

        # 👉 распознаем через OpenAI
        user_text = await voice_to_text(file_bytes.read())

        if not user_text:
            await message.answer("❌ Не удалось распознать речь")
            return

        # AI ответ
        answer = await process_voice_message(user_text)

        # отправляем текст
        await message.answer(f"🗣 You said: {user_text}\n\n{answer}")

        # 👉 голос
        voice_file = await text_to_voice(answer)

        if voice_file:
            await message.answer_voice(voice_file)

    except Exception as e:
        print("VOICE ERROR:", e)
        await message.answer("Something went wrong")