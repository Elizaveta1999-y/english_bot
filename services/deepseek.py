import requests
import os
import time
from config import DEEPSEEK_API_KEY

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def chat(prompt: str, max_tokens: int = 800, temperature: float = 0.6, retries: int = 2):
    messages = [{"role": "user", "content": prompt}]

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

    # --- Логирование для отладки ---
    print(f"Sending request to DeepSeek API. Last 200 chars of prompt: {prompt[-200:]}")
    # -----------------------------

    for attempt in range(retries + 1):
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            # --- Логирование успешного ответа ---
            print(f"DeepSeek API responded with status: {response.status_code}")
            # ----------------------------------

            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"DeepSeek API error (attempt {attempt+1}): {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                return "I'm having trouble responding. Please try again."