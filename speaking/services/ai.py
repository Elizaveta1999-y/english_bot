import requests
import os

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


SYSTEM_PROMPT = """
You are a friendly English tutor.
Always correct mistakes and ask questions.
"""


def transcribe_audio(audio_url: str):
    print("DOWNLOADING AUDIO:", audio_url)

    audio_file = requests.get(audio_url)

    print("SENDING TO WHISPER...")

    response = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        },
        files={
            "file": ("voice.ogg", audio_file.content)
        },
        data={
            "model": "gpt-4o-mini-transcribe"
        }
    )

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

    try:
        return response.json().get("text", "")
    except:
        return ""


async def process_voice_message(audio_url, mode, user_name=None):
    try:
        user_text = transcribe_audio(audio_url)

        print("USER SAID:", user_text)

        if not user_text:
            return "I didn't catch that. Can you repeat?"

        if mode == "name":
            return user_text.strip()

        response = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {TOGETHER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "meta-llama/Llama-3-8b-chat-hf",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
                "max_tokens": 120
            }
        )

        print("AI RESPONSE:", response.text)

        return response.json()["choices"][0]["message"]["content"]

    except Exception as e:
        print("ERROR:", str(e))
        return "Something went wrong"