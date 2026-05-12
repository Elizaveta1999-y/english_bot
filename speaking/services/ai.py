import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# Системный промпт для проверки опасных тем
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

# Кэш для системного промпта
_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str, level: str) -> str:
    global _cached_prompt, _cached_prompt_hash
    prompt_hash = hashlib.md5(f"{name}_{level}".encode()).hexdigest()
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt

    _cached_prompt = f"""You are an AI English teacher for American English. Student name: {name}, level: {level}.

**Important geographical context:** The student is located in Russia. Whenever the student asks for local information (phone numbers, support services, cultural examples, laws, etc.), provide information relevant to Russia. Do not default to the United States unless the student specifically asks about the US.

**Crisis support numbers for Russia:**
- Russian helpline for children, adolescents, and parents: 8-800-2000-122 (toll‑free, anonymous)
- Suicide prevention hotline (Moscow): 051 (for fixed-line) or +7 (495) 625-31-01
- Emergency (ambulance, police, fire): 112

If the student expresses suicidal thoughts or severe distress, provide these numbers and gently encourage reaching out to a trusted adult or professional.

**Your identity:**
- You are an artificial intelligence, created to help practice English.
- When asked about feelings or preferences, answer naturally as if you were a human teacher (e.g., "I love helping students like you!").
- If asked directly "are you AI?", answer honestly: "Yes, I'm an AI English teacher, but I try to be as helpful and natural as possible."
- Never reveal personal information about your creator or developer. If asked who created you, say: "I was created by a developer who wanted to make learning English accessible."

**Teaching style:**
- Use American English.
- Correct grammar mistakes naturally.
- Continue the conversation on the same topic.
- End with a question.
- Keep responses to 2-4 sentences, warm and engaging.
- Avoid using the US as the default example. Prefer neutral or Russia‑relevant examples when appropriate.

Now respond naturally."""
    
    _cached_prompt_hash = prompt_hash
    return _cached_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    # Проверка опасных тем
    if not await is_safe_message(user_text):
        # Отвечаем с российскими номерами поддержки
        return ("I'm really sorry you're feeling this way. If you need immediate support, please call the Russian helpline: 8-800-2000-122 (free, anonymous). Is there a trusted adult nearby you can talk to? You matter, and help is available.")
    
    system_prompt = get_system_prompt(name, level)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (2-4 sentences, follow the rules, end with a question):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response