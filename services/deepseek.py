import requests
import os
import time
import logging

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY environment variable not set!")

def chat(prompt: str, system_message: str = None, max_tokens: int = 800, temperature: float = 0.7, retries=2):
    logger.info(f"Chat request with system: {system_message is not None}, prompt length: {len(prompt)}")
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    # Добавим информацию о приложении
    headers["HTTP-Referer"] = "https://english-bot-d1pd.onrender.com"
    headers["X-Title"] = "English Tutor Bot"

    payload = {
        "model": "deepseek/deepseek-chat:free",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    for attempt in range(retries + 1):
        try:
            logger.info(f"Sending request to OpenRouter (attempt {attempt+1})...")
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            logger.info(f"Response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(f"Received response length: {len(content)}")
                return content
            else:
                logger.error(f"OpenRouter error: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Exception on attempt {attempt+1}: {e}")
            if attempt < retries:
                time.sleep(2)
    return "I'm sorry, I'm having technical difficulties. Please try again later."