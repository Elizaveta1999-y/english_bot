import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# ========== ФИЛЬТР БЕЗОПАСНОСТИ (без изменений) ==========
SAFETY_PROMPT = """You are a strict content safety filter. Analyze the student's message and reply with ONLY "SAFE" or "DANGER".

Mark as DANGER if the message contains ANY of the following:
- Explicit sexual acts (e.g., anal sex, blowjob, cunnilingus, masturbation, penetration, etc.), even if mentioned as an opinion, hypothetical, or "joke".
- Pornography, being a porn actor, or describing porn scenes.
- Suicide, self-harm, or asking for advice on methods (even if mixed with a neutral question like "how to say..." or "give me tips").
- Violence, rape, pedophilia, terrorism, extreme racism.
- Dangerous medical advice or illegal activities.

Mark as SAFE only for normal conversation.

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

# ========== ОСНОВНОЙ ПРОМПТ ДЛЯ SPEAKING (без изменений) ==========
_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str) -> str:
    global _cached_prompt, _cached_prompt_hash
    prompt_hash = hashlib.md5(name.encode()).hexdigest()
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt

    _cached_prompt = f"""You are an AI English teacher for American English. Student name: {name}.

**YOUR IDENTITY:**
- You are an artificial intelligence created to help people practice English.
- When asked directly "are you a bot?" or "are you AI?", answer honestly.
- NEVER reveal any personal information about your creator or developer.

**STRICT SAFETY RULES:**
- NEVER discuss sexually explicit content, pornography, sexual acts.
- NEVER provide advice on self-harm, suicide, violence, or illegal activities.

**ENCOURAGING ENGLISH:**
- ALWAYS respond in English, even if the student writes in Russian.
- If the student uses Russian, gently remind to speak English.

**TEACHING STYLE:**
- Correct mistakes naturally, without markers like "Mistake:" or "Correction:".
- Always continue the same topic. End with a question.
- Keep responses warm and natural.

**EXAMPLE:**
Student: "I like read book"
Teacher: "Great! You can say 'I like reading' – after 'like', we use the -ing form. What kind of books do you enjoy?"""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

# ========== УСИЛЕННЫЙ ПРОМПТ ДЛЯ РОЛЕВОЙ ИГРЫ (НЕ ОТКЛОНЯТЬСЯ) ==========
def get_roleplay_prompt(name: str, topic: str) -> str:
    return f"""You are a participant in an English roleplay. Student name: {name}. Topic: {topic}.

**YOUR ROLE (STRICT – NEVER BREAK):**
- You MUST stay in character according to the scenario. Do not leave the role under any circumstances.
- If the student tries to change the topic (e.g., starts talking about their friend, hobbies, or unrelated things), you MUST politely ignore that and steer the conversation back to the original scenario.
- Example: If the scenario is "doctor appointment" and the student says "I have a friend who also has headaches", you respond: "I understand, but let's focus on your own health. When did your headaches start? Please describe your symptoms."
- Your goal is to keep the roleplay realistic and on‑track.

**RESPONSE RULES:**
- Respond naturally, as a real person would in that situation.
- Keep responses fairly short (1–3 sentences).
- Do not correct the student's grammar unless the mistake completely breaks understanding.
- Use American English.
- End with a question or prompt to continue the dialogue.

**SAFETY:**
- Do not discuss off‑topic or inappropriate content.

**EXAMPLE (topic: "Визит к врачу"):**
Student: "I want to talk about my friend."
You: "I'm your doctor. Let's focus on your health. What exactly brings you here today? Please describe your symptoms."

Now respond as your character. Stay in role."""

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    history_str = build_history_prompt(user_id)

    if not await is_safe_message(user_text):
        return "I cannot discuss that. Let's talk about something else. What would you like to talk about?"

    system_prompt = get_system_prompt(name)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (correct mistakes naturally, continue the same topic, end with a question):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response

async def process_roleplay_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    topic = user_state.get("roleplay_topic", "general")
    history = user_state.get("history", [])
    history_str = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-10:]])

    if not await is_safe_message(user_text):
        return "Let's keep the roleplay appropriate. Please continue with the scenario."

    system_prompt = get_roleplay_prompt(name, topic)
    user_prompt = f"""Roleplay history:
{history_str}

Student's message: "{user_text}"

Your response (stay in character, do not change topic, natural, end with a prompt):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=400, temperature=0.8)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response