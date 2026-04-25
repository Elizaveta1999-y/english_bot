from aiogram import Router, F
from aiogram.types import Message
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
        error_voice = await text_to_voice("Sorry, I couldn't understand. Could you say that again?")
        if error_voice:
            await message.answer_voice(error_voice)
        return

    # Этап 1: ожидание имени
    if user_state.get("waiting_for_name"):
        set_user_name(user_id, user_text.strip())
        user_state["waiting_for_name"] = False
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)

        voice_msg = f"Nice to meet you, {user_text}! Let's practice English. Just speak naturally about anything. I'll correct your mistakes and we'll have a conversation. Go ahead, say something!"
        voice_file = await text_to_voice(voice_msg)
        if voice_file:
            await message.answer_voice(voice_file)
        return

    # Этап 2: активный диалог
    if user_state.get("mode") == "speaking_active":
        ai_response = await process_voice_message(user_id, user_text)
        voice_file = await text_to_voice(ai_response)
        if voice_file:
            await message.answer_voice(voice_file)
        else:
            await message.answer(ai_response)