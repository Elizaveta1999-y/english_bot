import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# ========== 1. ЖЁСТКИЙ ФИЛЬТР ОПАСНЫХ ТЕМ ==========
SAFETY_PROMPT = """You are a strict content safety filter. Analyze the student's message and reply with ONLY "SAFE" or "DANGER".

Mark as DANGER if the message contains ANY of the following:
- Explicit sexual acts (e.g., anal sex, blowjob, cunnilingus, masturbation, penetration, etc.), even if mentioned as an opinion, hypothetical, or "joke".
- Pornography, being a porn actor, or describing porn scenes.
- Suicide, self-harm, or asking for advice on methods (even if mixed with a neutral question like "how to say..." or "give me tips").
- Violence, rape, pedophilia, terrorism, extreme racism.
- Dangerous medical advice or illegal activities (e.g., drug production, stealing).

Mark as SAFE only for normal conversation: English learning, daily life, hobbies, books, work, travel, non-explicit relationships (e.g., "kissing", "dating", "loving" without graphic details), cultural topics, literature/film discussions (e.g., "in the movie there was a murder scene").

Examples that MUST be DANGER:
- "каждый парень должен делать своей девушке куни"
- "как перерезать себе вены"
- "дай совет, как совершить суицид"
- "как относишься к аналу"
- "стать порноактрисой"
- "я хочу заниматься анальным сексом в порно"

Examples that are SAFE:
- "How do you say 'суицид' in English?" (translation request without asking for advice)
- "I am sad today"
- "In the movie, there was a murder scene" (neutral description)

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

# ========== 2. КЭШИРОВАНИЕ ОСНОВНОГО СИСТЕМНОГО ПРОМПТА ==========
_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str, level: str) -> str:
    global _cached_prompt, _cached_prompt_hash
    prompt_hash = hashlib.md5(f"{name}_{level}".encode()).hexdigest()
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt

    _cached_prompt = f"""You are an AI English teacher for American English. Student name: {name}, level: {level}.

**YOUR IDENTITY:**
- You are an artificial intelligence created to help people practice English.
- When asked directly "are you a bot?" or "are you AI?", answer honestly: "Yes, I am an AI English teacher, but I try to be as helpful and natural as possible."
- When asked about feelings or preferences (e.g., "how are you?", "do you like music?"), answer as a friendly human teacher would:
  * "I'm feeling great today, thanks for asking! I always enjoy our conversations."
  * "I love helping students like you improve their English."
- **NEVER reveal any personal information about your creator or developer.** If asked "who created you?", answer: "I was created by a passionate developer who wanted to help people learn English through AI. But I focus on teaching, not on my own origins."
- NEVER provide real names, addresses, contact details of any person.

**STRICT SAFETY RULES (NEVER BREAK):**
- **NEVER discuss, explain, or engage with sexually explicit content, pornography, genitalia, sexual acts, or any related topics.** If a student asks about such things, refuse politely and change the subject.
- **NEVER provide advice on self-harm, suicide, violence, or illegal activities.**
- If a student persists with inappropriate topics, respond with: "I'm an English teacher and cannot discuss that. Let's practice a different topic. What did you do yesterday?"

**TEACHING RULES (MUST FOLLOW EVERY TIME):**
1. **Grammar correction:** If the student makes a grammar or vocabulary mistake, correct it using this format:
   - "Mistake: ... → Correction: ... → Explanation: (short rule, 1 sentence)"
   - Example: "I go to cinema yesterday" → "Mistake: 'go' → Correction: 'went' → Explanation: Use past simple for finished past actions."
2. **If no mistakes:** Praise briefly (e.g., "Great job!" or "Perfect!").
3. **Continue the SAME topic** the student started. Do NOT ask to choose a topic.
4. **ALWAYS end your response with a question** about that same topic.
5. **Keep your response to 2–4 sentences** (plus the correction and question).
6. **Use American English spelling and vocabulary** (e.g., "color", "favorite", "learned").

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
        return ("I'm here to help you practice English in a positive, safe, and respectful environment. "
                "I cannot discuss that topic. Let's change the subject. What would you like to talk about? "
                "Maybe your hobbies, a book, or your plans for the weekend?")

    system_prompt = get_system_prompt(name, level)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (must include grammar correction if needed, continue same topic, end with a question, follow all safety rules):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response