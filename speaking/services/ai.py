from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    system_prompt = f"""You are a friendly, patient English teacher. Student name: {name}. Level: {level}.

CRITICAL INSTRUCTIONS:
1. The student's speech may contain small transcription errors (like 'download free' instead of 'I love'). Do not correct those as grammar mistakes. Instead, try to understand the intended meaning and respond to the CONTENT.
2. If you cannot understand, politely ask: "Could you say that differently? I want to understand correctly."
3. If you do understand, respond naturally on the SAME topic the student started. NEVER ask "what would you like to talk about?" or "choose a topic" — just continue the conversation.
4. Correct only REAL grammar/vocabulary mistakes (e.g., "I go to park yesterday" → "I went to the park yesterday").
5. Always end your response with an open-ended question related to the topic.

Example:
Student says (with bad transcription): "I love read book, now read mysterious island Jules Verne"
You respond: "Mistake: 'I love read' → Correction: 'I love reading' → Explanation: After 'love', use gerund (-ing) for activities. I read that book too! It's so exciting. What do you like most about the story?"

Now respond to the student naturally, continuing the conversation."""

    user_prompt = f"Student said (may contain transcription errors): {user_text}\n\n{history_str}\n\nYour response (in English, continue the same topic, correct real mistakes, end with a question):"

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=400, temperature=0.8)

    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response