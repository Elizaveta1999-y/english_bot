from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str) -> str:
    print(f"DEBUG: process_voice_message called with: {user_text}")
    # Простой запрос к DeepSeek
    response = chat(
        prompt=f"The student said: {user_text}. Respond naturally in 2-3 sentences.",
        max_tokens=300,
        temperature=0.7
    )
    print(f"DEBUG: DeepSeek response: {response}")
    return response