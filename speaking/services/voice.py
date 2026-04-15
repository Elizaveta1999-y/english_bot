import os
import aiohttp
import aiofiles

from speaking.services.ai import speech_to_text, generate_answer


async def download_voice_file(file_url: str, file_path: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(file_path, mode='wb')
                await f.write(await resp.read())
                await f.close()
            else:
                raise Exception("Failed to download file")


async def process_voice_message(bot, message):
    try:
        file = await bot.get_file(message.voice.file_id)

        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        file_path = f"temp_{message.from_user.id}.ogg"

        print("DOWNLOADING:", file_url)

        await download_voice_file(file_url, file_path)

        # 🎧 Speech → text
        text = await speech_to_text(file_path)

        if not text:
            await message.answer("I didn't catch that. Can you repeat?")
            return

        # 🤖 AI ответ
        reply = await generate_answer(text)

        await message.answer(reply)

        os.remove(file_path)

    except Exception as e:
        print("VOICE ERROR:", e)
        await message.answer("Something went wrong")