import requests
import time
from config import DEEPSEEK_API_KEY

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def chat(prompt: str, system_message: str = None, max_tokens: int = 300, temperature: float = 0.7, retries=2):
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

    for attempt in range(retries + 1):
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"DeepSeek API error (attempt {attempt+1}): {e}")
            if attempt < retries:
                time.sleep(1)
            else:
                return "Sorry, I'm having trouble thinking. Please try again."