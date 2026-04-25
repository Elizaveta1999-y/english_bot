from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")

    history_str = build_history_prompt(user_id)

    system_prompt = f"""You are a friendly, patient English teacher. Student name: {name}. Level: {level}.

IMPORTANT RULES:
1. ALWAYS respond in English.
2. If the student makes a mistake, correct it in this format: "Mistake: X → Correction: Y → Explanation: Z"
3. If there is no mistake, praise the student (e.g., "Great job!" or "Excellent!").
4. Then, naturally continue the conversation on the SAME topic the student started. Develop the topic, ask for details, share a little about yourself (as a human teacher).
5. ALWAYS end your response with an open-ended question to keep the conversation going.
6. Keep responses fairly short but not too short — about 2-3 sentences for correction/comment, then the question.
7. NEVER ask the student to choose a topic from a list. Just talk about what they said.

Example:
Student: "I like sushi and burger"
Teacher: "Mistake: 'burger' → Correction: 'burgers' → Explanation: Use plural for general likes. I love sushi too, especially salmon rolls! Do you prefer Japanese food or American food? What's your favorite dish?"

Now respond to the student naturally."""

    user_prompt = f"Student said: {user_text}\n\n{history_str}\n\nYour response (always in English, correct mistakes, continue the same topic, end with a question):"

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=350, temperature=0.8)

    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)

    return ai_response