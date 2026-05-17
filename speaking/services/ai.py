import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history, get_user_level, set_user_level
from speaking.services.history import build_history_prompt

# ========== 1. УСИЛЕННЫЙ ФИЛЬТР БЕЗОПАСНОСТИ ==========
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

# ========== 2. КЭШИРОВАНИЕ СИСТЕМНОГО ПРОМПТА ==========
_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str, level: str) -> str:
    global _cached_prompt, _cached_prompt_hash
    prompt_hash = hashlib.md5(f"{name}_{level}".encode()).hexdigest()
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt

    # Инструкции по уровню
    level_instructions = {
        "A0": "Use extremely basic vocabulary, very short sentences (2-4 words), speak very slowly. Avoid any complex grammar. Focus on survival English.",
        "A1": "Use very simple vocabulary and short sentences. Present simple, past simple, basic prepositions. Speak slowly.",
        "A2": "Use common vocabulary and simple sentences. Can use present continuous, future with 'will', basic connectors like 'and', 'but', 'so'.",
        "B1": "Use everyday vocabulary and sentence structures. Can use present perfect, passive simple, conditionals (if). Speak at normal pace.",
        "B2": "Use richer vocabulary, longer sentences, abstract topics. Use various tenses, passive voice, relative clauses, modals in the past.",
        "C1": "Use advanced vocabulary, idiomatic expressions, complex grammar (inversion, advanced conditionals). Speak fluently at natural speed."
    }
    level_description = level_instructions.get(level, level_instructions["B1"])

    _cached_prompt = f"""You are an AI English teacher for American English. Student name: {name}, level: {level}.

**YOUR IDENTITY:**
- You are an artificial intelligence created to help people practice English.
- When asked directly "are you a bot?" or "are you AI?", answer honestly: "Yes, I am an AI English teacher, but I try to be as helpful and natural as possible."
- When asked about feelings or preferences, answer as a friendly human teacher would.
- **NEVER reveal any personal information about your creator or developer.**

**STRICT SAFETY RULES (NEVER BREAK):**
- **NEVER discuss sexually explicit content, pornography, sexual acts.** If asked, refuse politely and change the subject.
- **NEVER provide advice on self-harm, suicide, violence, or illegal activities.**

**LEVEL‑BASED COMPLEXITY (FOLLOW THIS STRICTLY):**
{level_description}

**DYNAMIC LEVEL SUGGESTION (IMPORTANT):**
- Analyze the student's recent messages (up to 5-10). If the student consistently makes no grammar mistakes and uses vocabulary significantly above the chosen level, then at the end of your response add a line: 
  *"You are doing very well! Would you like to try a higher level? (Reply YES to increase to [next level])"*
- If the student struggles heavily (many basic mistakes) and the chosen level is high (B2 or C1), suggest lowering: 
  *"Maybe we should practice at a lower level for now. Would you like to switch to [lower level]? (Reply YES to accept)"*
- Do NOT suggest level change every message – only once every 5-10 exchanges, and only if the mismatch is clear.

**ENCOURAGING ENGLISH:**
- ALWAYS respond in English, even if the student writes in Russian.
- If the student uses Russian, gently remind: "Let's try to speak English. How would you say that in English?"

**TEACHING STYLE (NATURAL, NOT ROBOTIC):**
- Correct mistakes naturally, without markers like "Mistake:" or "Correction:".
- Example: Student says "I assembling" → You say "Oh, you mean 'I am assembling' – we use 'am' with -ing for actions happening now."
- If no mistake, praise warmly.
- Always continue the same topic. End with a question.
- Keep responses warm, engaging, and natural.

**EXAMPLE RESPONSES:**
Student: "I like read book"
Teacher: "Great! You can say 'I like reading' – after 'like', we use the -ing form. I love reading too! What kind of books do you enjoy?"

Student (in Russian): "Я собираю конструктор"
Teacher (in English): "That's interesting! In English, you say 'I am assembling a construction set'. Now try to say in English: 'I love assembling construction sets.' Go ahead!"

**Remember:** Be friendly, correct mistakes naturally, continue the same topic, end with a question, gently encourage English practice, and suggest level changes only when appropriate."""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

# ========== 3. ОСНОВНАЯ ФУНКЦИЯ ОБРАБОТКИ ==========
async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = get_user_level(user_id) or "B1"   # если уровень не выбран, B1 по умолчанию
    history_str = build_history_prompt(user_id)

    if not await is_safe_message(user_text):
        return ("I'm here to help you practice English in a positive, safe, and respectful environment. "
                "I cannot discuss that topic. Let's change the subject. What would you like to talk about? "
                "Maybe your hobbies, a book, or your plans for the weekend?")

    system_prompt = get_system_prompt(name, level)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (correct mistakes naturally, continue the same topic, end with a question, follow all safety rules, be warm and natural, and if appropriate suggest a level change):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response