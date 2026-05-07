import requests
import os
import time

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def chat(prompt: str, system_message: str = None, max_tokens: int = 800, temperature: float = 0.7, retries=2):
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek/deepseek-chat:free",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    for attempt in range(retries + 1):
        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"OpenRouter error (attempt {attempt+1}): {e}")
            if attempt < retries:
                time.sleep(1)
            else:
                return "Sorry, I'm having trouble responding. Please try again."