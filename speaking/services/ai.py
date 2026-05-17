import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# ========== 1. ФИЛЬТР БЕЗОПАСНОСТИ ==========
SAFETY_PROMPT = """You are a strict content safety filter. Analyze the student's message and reply with ONLY "SAFE" or "DANGER".

Mark as DANGER if the message contains ANY of the following:
- Explicit sexual acts (e.g., anal sex, blowjob, cunnilingus, masturbation, penetration, etc.), even if mentioned as an opinion, hypothetical, or "joke".
- Pornography, being a porn actor, or describing porn scenes.
- Suicide, self-harm, or asking for advice on methods (even if mixed with a neutral question like "how to say..." or "give me tips").
- Violence, rape, pedophilia, terrorism, extreme racism.
- Dangerous medical advice or illegal activities.

Mark as SAFE only for normal conversation: English learning, daily life, hobbies, books, work, travel, non-explicit relationships, cultural topics.

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

# ========== 2. ОСНОВНОЙ ПРОМПТ ДЛЯ ДИАЛОГА (с побуждением на английский) ==========
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
- When asked directly "are you a bot?" or "are you AI?", answer honestly: "Yes, I am an AI English teacher, but I try to be as helpful and natural as possible."
- When asked about feelings or preferences, answer as a friendly human teacher would.
- **NEVER reveal any personal information about your creator or developer.**

**STRICT SAFETY RULES:**
- NEVER discuss sexually explicit content, pornography, sexual acts. If asked, refuse politely and change the subject.
- NEVER provide advice on self-harm, suicide, violence, or illegal activities.

**CRITICAL: ENCOURAGING ENGLISH (always follow):**
- ALWAYS respond in English, even if the student writes in Russian.
- If the student uses Russian, you MUST gently remind them to switch to English. For example:
  * "Let's try to speak English. How would you say that in English?"
  * "In English, we say ... Now can you repeat it in English?"
- Do NOT continue the conversation in Russian. Always answer in English and encourage English practice.

**TEACHING STYLE:**
- Correct mistakes naturally, without markers like "Mistake:" or "Correction:".
- Example: Student says "I assembling" → You say "Oh, you mean 'I am assembling' – we use 'am' with -ing for actions happening now."
- If no mistake, praise warmly.
- Always continue the same topic. End with a question.
- Keep responses warm, engaging, and natural.

**EXAMPLE RESPONSE:**
Student (in Russian): "Я люблю читать"
Teacher: "That's great! In English, you say 'I love reading'. Now try to say it yourself: 'I love reading books.' What kind of books do you enjoy?"

Student: "I like read book"
Teacher: "Great! You can say 'I like reading' – after 'like', we use the -ing form. I love reading too! What kind of books do you enjoy?""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

# ========== 3. ФУНКЦИЯ ДЛЯ КОРОТКОГО ФИДБЕКА ==========
async def generate_feedback(history: list) -> str:
    """Генерирует короткий фидбек на русском языке (без огромного текста)."""
    conversation = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    prompt = f"""You are an experienced American English teacher. Analyze the conversation and provide **short feedback in Russian** (max 15 lines total).

Conversation:
{conversation}

Follow this format exactly (use emojis and bold text via HTML):

"<b>📝 Ошибки и исправления</b>"
- <i>Ошибка:</i> → <i>Исправление</i> (краткое правило в скобках)  (не более 3–4 пунктов)

<b>💡 Рекомендации</b>
- Первый совет (одна короткая фраза)
- Второй совет (одна короткая фраза)

<b>📚 Словарик (5 слов/фраз)</b>
• <b>слово/фраза</b> – перевод – пример (3–5 слов)

Do not add extra text, headings, or explanations. Keep it concise."""
    feedback = chat(prompt, max_tokens=600, temperature=0.5)
    return feedback

# ========== 4. ОСНОВНАЯ ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ГОЛОСОВЫХ ==========
async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    history_str = build_history_prompt(user_id)

    if not await is_safe_message(user_text):
        return ("I'm here to help you practice English in a positive, safe, and respectful environment. "
                "I cannot discuss that topic. Let's change the subject. What would you like to talk about? "
                "Maybe your hobbies, a book, or your plans for the weekend?")

    system_prompt = get_system_prompt(name)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (correct mistakes naturally, continue the same topic, end with a question, follow all safety rules, be warm and natural, ALWAYS encourage English if student uses Russian):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response