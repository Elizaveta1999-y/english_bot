import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def ask_gpt(text: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты дружелюбный преподаватель английского."},
                {"role": "user", "content": text}
            ]
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"❌ Ошибка OpenAI: {e}"