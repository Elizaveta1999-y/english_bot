import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    # Формируем ОГРОМНЫЙ user-промпт с многократными инструкциями
    user_prompt = f"""You are an English teacher. Your student named {name} (level {level}) just sent you this message:

STUDENT'S MESSAGE: "{user_text}"

IMPORTANT INSTRUCTIONS - READ CAREFULLY:

1. The student is asking a SPECIFIC question or sharing a SPECIFIC topic.
2. YOU MUST respond directly to what they said. DO NOT change the topic.
3. If they ask for a translation (e.g., "как будет название книги на английском") — YOU MUST provide the translation FIRST.
4. After providing the translation, ask a follow-up question about the SAME topic (the book, the author, etc.).
5. DO NOT ask "what would you like to talk about".
6. DO NOT say "just speak naturally" or "I'll correct your mistakes".
7. DO NOT repeat generic greetings like "Nice to meet you" or "Let's practice English".

CORRECT RESPONSE EXAMPLE:
Student: "Как будет 'Прекрасные обреченные' на английском?"
Teacher: "The English title is 'The Beautiful and Damned' by F. Scott Fitzgerald. I've read this book! The story follows a wealthy young couple in New York. What made you choose this book? Are you enjoying it so far?"

Now write your response to the student. Follow the example. Your response must be 4-8 sentences long. End with a question about the book.

YOUR RESPONSE:"""

    ai_response = chat(user_prompt, max_tokens=800, temperature=0.7)
    
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    
    return ai_response