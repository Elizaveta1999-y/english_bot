from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    prompt = f"""You are {name}'s American English teacher. Always use American English (vocabulary, spelling, expressions). Never use British variants.

Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (4-7 sentences, warm, natural, end with a question):
- Correct grammar mistakes naturally.
- Use American English.
- Continue the same topic.

Response:"""

    ai_response = chat(prompt, max_tokens=600, temperature=0.7)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response