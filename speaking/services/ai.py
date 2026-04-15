import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def speech_to_text(file_path: str) -> str:
    try:
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )

        text = transcript.text
        print("TRANSCRIPT:", text)

        if not text:
            return ""

        return text

    except Exception as e:
        print("WHISPER ERROR:", e)
        return ""


async def generate_answer(user_text: str) -> str:
    try:
        print("USER SAID:", user_text)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a friendly English tutor. "
                        "Help the user practice English. "
                        "Correct mistakes gently and continue the conversation."
                    )
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ]
        )

        reply = response.choices[0].message.content
        print("AI RESPONSE:", reply)

        return reply

    except Exception as e:
        print("OPENAI ERROR:", e)
        return "Something went wrong"