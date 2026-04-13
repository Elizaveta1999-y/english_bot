from aiogram import Router
from aiogram.types import Message, ContentType

from services.ai import process_voice_message
from services.tts import text_to_voice
from services.storage import get_user_state, set_user_name

router = Router()


@router.message(lambda message: message.content_type == ContentType.VOICE)
async def handle_voice(message: Message):
    print("VOICE HANDLER TRIGGERED")  # 👈 лог

    user_id = message.from_user.id
    state = get_user_state(user_id)

    # ❗ Проверяем режим
    if state.get("mode") != "speaking":
        return

    # Скачиваем файл
    file = await message.bot.get_file(message.voice.file_id)
    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"

    # 🔹 Если нет имени
    if not state.get("name"):
        name = await process_voice_message(file_url, mode="name")

        set_user_name(user_id, name)

        response_text = f"""
Nice to meet you, {name}!
Please choose a topic to talk about:
Which one sounds interesting to you?
"""

        voice = await text_to_voice(response_text)
        await message.answer_voice(voice)
        return

    # 🔹 Основной диалог
    response_text = await process_voice_message(
        file_url,
        mode="dialog",
        user_name=state["name"]
    )

    voice = await text_to_voice(response_text)
    await message.answer_voice(voice)