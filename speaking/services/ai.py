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
                    "content": (
                        "You are an English tutor.\n"
                        "1. If the user made a mistake — correct it.\n"
                        "2. Explain briefly.\n"
                        "3. Ask a follow-up question.\n"
                        "Keep it short and simple."
                    )
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            max_tokens=150
        )

        return response.choices[0].message.content

    except Exception as e:
        print("AI ERROR:", e)
        return "I didn't understand. Try again."