import requests
import os

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


SYSTEM_PROMPT = """
You are a friendly and patient English tutor.

Your goal is to help the user practice speaking English.

RULES:

1. Keep answers SHORT (2-4 sentences)

2. If mistake:
- correct
- show correct sentence
- explain simply

3. If no mistakes:
- praise

4. Always ask a question
"""


def transcribe_audio(audio_url: str):
    audio_file = requests.get(audio_url)

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

    return response.json().get("text", "")


async def process_voice_message(audio_url, mode, user_name=None):
    try:
        user_text = transcribe_audio(audio_url)

        if not user_text:
            return "Sorry, I didn't hear you clearly. Can you repeat?"

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
                    {
                        "role": "user",
                        "content": f"{user_name} said: {user_text}"
                    }
                ],
                "max_tokens": 120,
                "temperature": 0.7
            }
        )

        return response.json()["choices"][0]["message"]["content"]

    except Exception as e:
        print("ERROR:", str(e))
        return "Something went wrong. Let's try again!"