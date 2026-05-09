from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    history_str = build_history_prompt(user_id)

    # Усиленный промпт, строго запрещающий приветствия после начала диалога
    prompt = f"""You are {name}'s English teacher. 

IMPORTANT: The conversation has already started. DO NOT introduce yourself, DO NOT say "Nice to meet you", DO NOT ask to choose a topic. 

Instead:
1. React to what {name} just said: "{user_text}"
2. If there is a grammar mistake, correct it naturally (example: "Instead of 'I love read', say 'I love reading' because...").
3. Ask a specific question about the SAME topic (books, food, travel, etc.) to continue the conversation.

CONVERSATION HISTORY (for context):
{history_str}

Student's last message: "{user_text}"

Your response (2-4 sentences, no greetings, end with a question):"""

    ai_response = chat(prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response