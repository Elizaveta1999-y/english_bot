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

    print(f"1. Got voice from user {user_id}")

    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    
    print("2. Downloaded voice file")
    
    user_text = await voice_to_text(file_bytes.read())
    print(f"3. Recognized text: '{user_text}'")
    
    if not user_text:
        print("4. No text recognized, sending error")
        await message.answer("Sorry, I couldn't understand. Please try again.")
        return

    if user_state.get("waiting_for_name"):
        print("5. Waiting for name, processing name")
        name = user_text.strip().split()[0][:20]
        set_user_name(user_id, name)
        user_state["waiting_for_name"] = False
        set_user_mode(user_id, "speaking_active")
        set_user_state(user_id, user_state)
        
        response_text = f"Nice to meet you, {name}! Let's practice English. Just speak naturally. I'll correct your mistakes. Go ahead!"
        print(f"6. Generated name response: {response_text[:50]}...")
        voice_path = await text_to_voice(response_text)
        if voice_path:
            await message.answer_voice(FSInputFile(voice_path))
            os.unlink(voice_path)
        return

    if user_state.get("mode") == "speaking_active":
        print("7. Calling process_voice_message...")
        ai_response = await process_voice_message(user_id, user_text)
        print(f"8. AI response: {ai_response[:100]}...")
        voice_path = await text_to_voice(ai_response)
        if voice_path:
            print("9. Sending voice response")
            await message.answer_voice(FSInputFile(voice_path))
            os.unlink(voice_path)
        else:
            print("9b. Sending text response (TTS failed)")
            await message.answer(ai_response)
    else:
        print("10. No active mode, sending fallback")
        await message.answer("Please press the '🎤 Speaking' button first!")