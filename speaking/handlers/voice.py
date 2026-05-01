import os
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from data.users import set_user_name, set_user_mode, get_user_state, set_user_state

router = Router()

@router.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    
    user_text = await voice_to_text(file_bytes.read())
    
    if not user_text:
        await message.answer("Sorry, I couldn't understand. Please try again.")
        return

    if user_state.get("waiting_for_name"):
        name = user_text.strip().split()[0][:20]
        set_user_name(user_id, name)
        user_state["waiting_for_name"] = False
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)

        voice_msg = f"Nice to meet you, {name}! Let's practice English. Just speak naturally. I'll correct your mistakes. Go ahead, say something!"
        voice_path = await text_to_voice(voice_msg)
        if voice_path:
            # ✅ Исправлено: используем FSInputFile
            audio = FSInputFile(voice_path)
            await message.answer_voice(audio)
            os.unlink(voice_path)
        return

    if user_state.get("mode") == "speaking_active":
        ai_response = await process_voice_message(user_id, user_text)
        voice_path = await text_to_voice(ai_response)
        if voice_path:
            # ✅ Исправлено: используем FSInputFile
            audio = FSInputFile(voice_path)
            await message.answer_voice(audio)
            os.unlink(voice_path)
        else:
            await message.answer(ai_response)