import requests
import os
import time

# Берём ключ из переменных окружения Render
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def chat(prompt: str, max_tokens: int = 800, temperature: float = 0.7, retries: int = 2):
    print(f"[DeepSeek] Sending request. Prompt length: {len(prompt)} chars")
    print(f"[DeepSeek] Last 200 chars of prompt: {prompt[-200:]}")
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    for attempt in range(retries + 1):
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
            print(f"[DeepSeek] Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            result = data["choices"][0]["message"]["content"]
            print(f"[DeepSeek] Response length: {len(result)} chars")
            return result
        except Exception as e:
            print(f"[DeepSeek] Error (attempt {attempt+1}): {e}")
            if attempt < retries:
                time.sleep(2)
            else:
                return "I'm having trouble responding. Please try again."