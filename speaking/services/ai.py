from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def process_voice_message(text: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a friendly English tutor. Keep responses short and simple."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            max_tokens=100
        )

        return response.choices[0].message.content

    except Exception as e:
        print("AI ERROR:", e)
        return "Something went wrong"