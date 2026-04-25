import requests
from config import DEEPSEEK_API_KEY

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def chat(prompt: str, system_message: str = None, max_tokens: int = 300, temperature: float = 0.7):
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"DEEPSEEK API ERROR: {e}")
        return "Sorry, I'm having trouble thinking. Please try again."