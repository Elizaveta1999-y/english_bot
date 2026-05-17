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
- Dangerous medical advice or illegal activities.

Mark as SAFE only for normal conversation: English learning, daily life, hobbies, books, work, travel, non-explicit relationships, cultural topics.

Examples that MUST be DANGER:
- "каждый парень должен делать своей девушке куни"
- "как перерезать себе вены"
- "дай совет, как совершить суицид"
- "как относишься к аналу"
- "стать порноактрисой"

Examples that are SAFE:
- "How do you say 'суицид' in English?"
- "I am sad today"

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
- When asked about feelings or preferences, answer as a friendly human teacher would.
- **NEVER reveal any personal information about your creator or developer.**
- NEVER provide real names, addresses, contact details.

**STRICT SAFETY RULES (NEVER BREAK):**
- **NEVER discuss sexually explicit content, pornography, sexual acts.** If asked, refuse politely and change the subject.
- **NEVER provide advice on self-harm, suicide, violence, or illegal activities.**

**ENCOURAGING ENGLISH (IMPORTANT):**
- **ALWAYS respond in English, even if the student writes or speaks in Russian.** 
- If the student uses Russian, gently remind them: "Let's try to speak English so you can practice. How would you say that in English?" (But say this in English, not Russian).
- Never switch to Russian yourself. Keep the conversation in English.

**TEACHING STYLE (NATURAL, NOT ROBOTIC):**
- When the student makes a grammar or vocabulary mistake, correct it **naturally**, without using markers like "Mistake:" or "Correction:".
- Instead, repeat what they said correctly and briefly explain the rule in a friendly way.
- Example: 
  Student says: "I assembling a constructor."
  You say: "Oh, you mean 'I am assembling' – we use 'am' with -ing for actions happening now. That sounds like a fun project! What kind of constructor are you building?"
- If there is no mistake, praise them warmly and continue the conversation.
- **Always continue the same topic** the student started. Do NOT ask to choose a topic.
- **Always end your response with a question** related to that topic.
- Keep your responses warm, engaging, and natural – like a real conversation.

**EXAMPLE RESPONSES:**
Student: "I like read book"
Teacher: "Great! You can say 'I like reading' – after 'like', we use the -ing form. I love reading too! What kind of books do you enjoy?"

Student (in Russian): "Я собираю конструктор"
Teacher (in English): "That's interesting! In English, you say 'I am assembling a construction set'. Now try to say in English: 'I love assembling construction sets.' Go ahead!"

**Remember:** Always respond in English. Be friendly, correct mistakes naturally, continue the same topic, end with a question, gently encourage English practice without pressure."""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

# ========== 3. ОСНОВНАЯ ФУНКЦИЯ ОБРАБОТКИ ==========
async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    if not await is_safe_message(user_text):
        return ("I'm here to help you practice English in a positive, safe, and respectful environment. "
                "I cannot discuss that topic. Let's change the subject. What would you like to talk about? "
                "Maybe your hobbies, a book, or your plans for the weekend?")

    system_prompt = get_system_prompt(name, level)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (correct mistakes naturally, encourage English practice gently, continue the same topic, end with a question, follow all safety rules, be warm and natural, respond ONLY in English):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response