from openai import OpenAI
from config import DEEPSEEK_API_KEY

# Инициализируем клиент DeepSeek (через библиотеку OpenAI, но с другим base_url)
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
    
    response = deepseek_client.chat.completions.create(
        model="deepseek-chat",  # используем актуальную модель
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )
    return response.choices[0].message.content