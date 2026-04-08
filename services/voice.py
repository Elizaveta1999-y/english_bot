import aiohttp
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE

async def tts(text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}"

    async with aiohttp.ClientSession() as s:
        async with s.post(url,
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            json={"text": text}
        ) as r:
            return await r.read()