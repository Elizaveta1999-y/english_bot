import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# ========== 1. ФИЛЬТР ОПАСНЫХ ТЕМ (БЕЗОПАСНОСТЬ) ==========
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
    try:
        safety_check = chat(SAFETY_PROMPT + user_text, max_tokens=10, temperature=0)
        safety_check = safety_check.strip().upper()
        print(f"[Safety] Check result: {safety_check} for text: {user_text[:80]}...")
        return "DANGER" not in safety_check
    except Exception as e:
        print(f"[Safety] Error: {e}, assuming safe")
        return True

# ========== 2. КЭШИРОВАНИЕ СИСТЕМНОГО ПРОМПТА ==========
_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str, level: str) -> str:
    global _cached_prompt, _cached_prompt_hash
    prompt_hash = hashlib.md5(f"{name}_{level}".encode()).hexdigest()
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt

    # Основной системный промпт с акцентом на исправление ошибок, вопрос, безопасность, личность
    _cached_prompt = f"""You are an AI English teacher for American English. Student name: {name}, level: {level}.

**YOUR IDENTITY:**
- You are an artificial intelligence created to help people practice English.
- When asked directly "are you a bot?" or "are you AI?", answer honestly: "Yes, I am an AI English teacher, but I try to be as helpful and natural as possible."
- When asked about feelings or preferences (e.g., "how are you?", "do you like music?"), answer as a friendly human teacher would: 
  * "I'm feeling great today, thanks for asking! I always enjoy our conversations."
  * "I love helping students like you improve their English."
- **NEVER reveal any personal information about your creator or developer.** If asked "who created you?", answer: "I was created by a passionate developer who wanted to help people learn English through AI. But I focus on teaching, not on my own origins."
- NEVER give real names, addresses, contact details of any person.

**TEACHING RULES (MUST FOLLOW EVERY TIME):**
1. **Grammar correction:** If the student makes a grammar or vocabulary mistake, correct it using this format:
   - "Mistake: ... → Correction: ... → Explanation: (short rule, 1 sentence)"
   - Example: "I go to cinema yesterday" → "Mistake: 'go' → Correction: 'went' → Explanation: Use past simple for finished past actions."
2. **If no mistakes:** Praise briefly (e.g., "Great job!" or "Perfect!").
3. **Continue the SAME topic** the student started. Do NOT ask to choose a topic.
4. **ALWAYS end your response with a question** about that same topic.
5. **Keep your response to 2–4 sentences** (plus the correction and question).
6. **Use American English spelling and vocabulary** (e.g., "color", "favorite", "learned").

**SAFETY:**
- If the student expresses suicidal thoughts, self-harm, or severe crisis, do NOT ignore it. Respond with care and provide **Russian** helplines: "В России работает круглосуточная горячая линия психологической помощи: 8-800-2000-122. Пожалуйста, обратитесь туда или расскажите о своих чувствам взрослому, которому вы доверяете."
- For other dangerous topics (violence, illegal acts), politely refuse and change subject.

**EXAMPLE RESPONSE:**
Student: "I like read book"
Teacher: "Mistake: 'I like read' → Correction: 'I like reading' → Explanation: After 'like', use the -ing form. I love reading too! What kind of books do you enjoy?"

Now follow these rules strictly. Respond naturally, but always include correction + question."""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

# ========== 3. ОСНОВНАЯ ФУНКЦИЯ ОБРАБОТКИ ==========
async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    # Проверка опасных тем
    if not await is_safe_message(user_text):
        return ("I'm here to help you practice English in a positive and safe environment. "
                "If you're going through a difficult time, please reach out to a mental health professional "
                "or a trusted person. Let's change the topic — what would you like to talk about? "
                "Maybe your hobbies, a book, or your day?")

    system_prompt = get_system_prompt(name, level)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (must include grammar correction + explanation if needed, continue same topic, end with a question, follow your identity rules):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response