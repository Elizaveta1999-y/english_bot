from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str) -> str:
    print(f"[AI] Processing message: {user_text}")
    # Максимально простой запрос без системных сообщений
    prompt = f"""You are a friendly English teacher. The student said: "{user_text}"

Reply in 2-3 sentences. Correct any grammar mistakes. End with a question about the same topic.

Your response:"""
    
    response = chat(prompt, max_tokens=300, temperature=0.7)
    print(f"[AI] Response: {response}")
    return response