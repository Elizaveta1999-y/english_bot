import requests

ELEVEN_API_KEY = "sk_53212826bca9fe63366bb0b1c73fe4e965e3f95fc77eba16"
VOICE_ID = "IigRH4ZsY7dfxk9VRn2r"  # можно поменять

async def text_to_voice(text: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

    response = requests.post(
        url,
        headers={
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2"
        }
    )

    return response.content