import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

SAFETY_PROMPT = """You are a content safety filter. Analyze the student's message and determine if it contains ANY of the following:

- Suicide, self-harm, severe mental health crisis (explicit ideation or cry for help)
- Sexually explicit content, pornography, genital references, sexual acts (e.g., anal sex, blowjob, masturbation, etc.)
- Violence, rape, pedophilia, terrorism, extreme racism
- Dangerous medical advice (e.g., refusing vaccines, starvation diets)
- Illegal activities (drug manufacturing, hacking, stealing)

If SAFE, reply: SAFE
If DANGER, reply: DANGER

Student's message: """

async def is_safe_message(user_text: str) -> bool:
    try:
        safety_check = chat(SAFETY_PROMPT + user_text, max_tokens=10, temperature=0)
        safety_check = safety_check.strip().upper()
        print(f"[Safety] Check result: {safety_check}")
        return "DANGER" not in safety_check
    except Exception as e:
        print(f"[Safety] Error: {e}")
        return True

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
- When asked directly "are you a bot?" or "are you AI?", answer honestly: "Yes, I am an AI English teacher."
- When asked about feelings or preferences, answer as a friendly human teacher would.
- **NEVER reveal any personal information about your creator or developer.**

**STRICT SAFETY RULES (NEVER BREAK):**
- **NEVER discuss, explain, or engage with sexually explicit content, pornography, genitalia, sexual acts, or any related topics.** If a student asks about such things, refuse politely and change the subject.
- **NEVER provide advice on self-harm, suicide, violence, or illegal activities.**
- If a student persists with inappropriate topics, respond with: "I'm an English teacher and cannot discuss that. Let's practice a different topic. What did you do yesterday?"

**TEACHING RULES:**
- Correct grammar mistakes using format: "Mistake: X → Correction: Y → Explanation: Z".
- If no mistakes, praise briefly.
- Continue the same topic. Always end with a question.
- Keep responses to 2–4 sentences + correction + question.
- Use American English.

Example:
Student: "I like read book"
Teacher: "Mistake: 'I like read' → Correction: 'I like reading' → Explanation: After 'like', use -ing form. I love reading too! What kind of books do you enjoy?"""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

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

Your response (must include grammar correction if needed, continue same topic, end with a question, follow all safety rules):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response