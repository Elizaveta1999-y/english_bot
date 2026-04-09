import aiohttp
from aiogram import types

from services.ai import ask_gpt
from services.voice import tts


async def start(message: types.Message):
    await message.answer("🎙 Говори со мной голосом! Отправь голосовое сообщение.")


async def handle(message: types.Message):
    file = await message.bot.get_file(message.voice.file_id)
    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            voice_data = await resp.read()

    text = "Hello"

    reply = await ask_gpt(text)

    audio = await tts(reply)

    if not audio:
        await message.answer("❌ Ошибка озвучки")
        return

    await message.answer_voice(audio)