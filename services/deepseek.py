from openai import OpenAI
from config import DEEPSEEK_API_KEY

# Инициализируем клиент DeepSeek
deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

def chat(prompt: str, system_message: str = None, max_tokens: int = 300, temperature: float = 0.7):
    """Универсальная функция для общения с DeepSeek"""
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"DEEPSEEK API ERROR: {e}")
        return "I'm sorry, I'm having trouble thinking right now. Please try again."