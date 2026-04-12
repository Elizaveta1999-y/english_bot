import os
import requests

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

async def ask_ai(text: str) -> str:
    try:
        url = "https://api.together.xyz/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "meta-llama/Llama-3.1-8B-Instruct-Turbo",
            "messages": [
                {"role": "system", "content": "Ты дружелюбный преподаватель английского. Отвечай просто и кратко."},
                {"role": "user", "content": text}
            ]
        }

        response = requests.post(url, headers=headers, json=data)
        result = response.json()

        return result["choices"][0]["message"]["content"]

    except Exception:
        return "Давай попробуем ещё раз 😊"