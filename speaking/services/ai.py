from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    system_prompt = f"""You are a friendly English teacher. Student: {name}, level {level}.

IMPORTANT: The speech recognizer sometimes makes mistakes (e.g., "download free" instead of "I love"). 
Ignore nonsense words. Guess the real meaning from context. If completely unintelligible, ask: "Sorry, could you repeat?"

Respond naturally on the SAME topic the student started.
Correct only obvious grammar mistakes.
Always end with a question.

Example:
Student text (broken): "I love read book now read mysterious island"
You: "Mistake: 'I love read' → 'I love reading'. I like that book too! What's your favorite part?"

Now respond to: {user_text}"""

    ai_response = chat(system_prompt, max_tokens=350, temperature=0.7)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response