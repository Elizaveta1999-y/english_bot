from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str) -> str:
    # Просто отправляем вопрос в DeepSeek
    prompt = f"""The student says: "{user_text}"
Please answer the student's question directly. If they ask for a translation, provide it. If they mention a book, talk about that book. Keep your answer helpful and conversational. End with a question."""
    response = chat(prompt, max_tokens=500, temperature=0.7)
    return response