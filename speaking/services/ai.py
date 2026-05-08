from services.deepseek import chat
from data.users import add_to_history

async def process_voice_message(user_id: int, user_text: str) -> str:
    # Просто отправляем текст пользователя в DeepSeek и возвращаем ответ
    prompt = f"The user said: {user_text}\n\nPlease respond directly and conversationally, answering any questions and continuing the topic. Do not ask to choose a topic."
    
    ai_response = chat(prompt, max_tokens=500, temperature=0.7)
    
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    
    return ai_response