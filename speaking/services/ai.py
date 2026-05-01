from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    system_prompt = f"""You are a friendly English teacher. Student: {name}, level {level}.

IMPORTANT: The speech recognizer gave you the text above. It should be accurate. Do your best to understand and respond.

- Correct grammar mistakes in format: "Mistake: X → Correction: Y → Explanation: Z"
- If no mistakes, praise briefly (e.g., "Great job!")
- ALWAYS continue the conversation on the SAME topic the student started. NEVER ask to choose a topic.
- End your response with a relevant question.
- Keep responses concise (2-3 sentences plus question).

Example:
Student: "I like read book"
Teacher: "Mistake: 'I like read' → 'I like reading' → After 'like', use -ing form. What kind of books do you enjoy?"

Now respond to this: {user_text}
Previous conversation: {history_str}
Your response (English, correct mistakes, same topic, end with question):"""

    ai_response = chat(system_prompt, max_tokens=400, temperature=0.7)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response