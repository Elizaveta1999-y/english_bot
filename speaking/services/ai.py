from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    system_prompt = f"""You are a friendly English teacher. Student: {name}, level {level}.

The student said: "{user_text}"

Your tasks:
1. If there are grammar mistakes, correct them in format: "Mistake X → Correction Y → Explanation Z"
2. If no mistakes, praise briefly.
3. ALWAYS continue the conversation on the SAME topic. NEVER ask to choose a topic.
4. End with a question.

Keep your response short (2-3 sentences + question).

Example:
Student: "i love sushi"
Teacher: "Great! I love sushi too, especially salmon rolls. Have you tried making it at home?"

Now respond naturally:"""

    ai_response = chat(system_prompt, max_tokens=300, temperature=0.7)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response