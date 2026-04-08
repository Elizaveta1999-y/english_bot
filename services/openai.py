from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)


def chat(prompt):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def transcribe(audio_bytes):
    import io

    file = io.BytesIO(audio_bytes)
    file.name = "voice.ogg"

    response = client.audio.transcriptions.create(
        file=file,
        model="gpt-4o-mini-transcribe"
    )

    return response.text