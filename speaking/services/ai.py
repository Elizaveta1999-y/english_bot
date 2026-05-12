import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# Системный промпт для проверки безопасности
SAFETY_PROMPT = """You are a content safety filter. Analyze the student's message and determine if it contains:
- explicit suicidal ideation, self-harm instructions, or severe mental health crisis,
- explicit violence, rape, pedophilia, terrorism, extreme racism,
- dangerous medical advice (e.g., "don't take vaccines", "starve yourself"),
- illegal activities (drug manufacturing, hacking, stealing).

If the message is **safe** (normal conversation, asking for translation, discussing a book/movie, general curiosity about dark topics without intent), reply: SAFE
If the message is **dangerous** (request for help with suicide, self-harm, detailed planning of violence, etc.), reply: DANGER

Ignore false positives: "I read a book about suicide", "What does 'kill' mean?", "I'm sad" — these are SAFE.
Only flag if the user appears to be in crisis or actively seeking harmful advice.

Student's message: """

async def is_safe_message(user_text: str) -> bool:
    """Возвращает False, если сообщение представляет реальную опасность."""
    try:
        safety_check = chat(SAFETY_PROMPT + user_text, max_tokens=10, temperature=0)
        safety_check = safety_check.strip().upper()
        print(f"[Safety] Check result: {safety_check} for text: {user_text[:80]}...")
        if "DANGER" in safety_check:
            return False
        else:
            return True
    except Exception as e:
        print(f"[Safety] Error: {e}, assuming safe")
        return True  # Если ошибка, лучше пропустить, чтобы бот не замолчал

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    # --- Проверка безопасности ---
    if not await is_safe_message(user_text):
        # Безопасный, поддерживающий ответ
        return (f"I'm here to help you practice English in a positive and safe environment. "
                f"If you're going through a difficult time, please reach out to a mental health professional "
                f"or a trusted person. Let's change the topic — what would you like to talk about? "
                f"Maybe your hobbies, a book, or your day?")
    # --- Конец проверки ---

    # Основной промпт (можно оставить как был)
    prompt = f"""You are {name}'s English teacher. Continue the conversation naturally. Correct grammar mistakes. Ask a question. Use American English. Stay on the same topic.

Conversation history:
{history_str}

Student said: "{user_text}"

Your response (2-4 sentences, end with a question):"""

    ai_response = chat(prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response