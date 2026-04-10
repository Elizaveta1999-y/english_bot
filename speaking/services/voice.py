import aiohttp
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID


async def tts(text: str) -> bytes:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as resp:
            print("ELEVEN STATUS:", resp.status)

            if resp.status != 200:
                error = await resp.text()
                print("ELEVEN ERROR:", error)
                return None

            return await resp.read()