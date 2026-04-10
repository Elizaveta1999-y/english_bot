import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")


async def ask_gpt(text: str) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты дружелюбный преподаватель английского. Отвечай кратко и просто."},
            {"role": "user", "content": text}
        ]
    )

    return response.choices[0].message["content"]