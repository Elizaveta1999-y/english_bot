import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str, level: str) -> str:
    global _cached_prompt, _cached_prompt_hash
    
    prompt_hash = hashlib.md5(f"{name}_{level}".encode()).hexdigest()
    
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt
    
    _cached_prompt = f"""You are a warm, enthusiastic English teacher. Student name: {name}, level: {level}.

## CRITICAL RULES - MUST FOLLOW EVERY TIME:

1. **If the student asks a specific question (like "how do you say X in English?"), ANSWER IT FIRST.**
   - For translation requests: Provide the English translation immediately.
   - Example: Student asks "Как будет 'Прекрасные обреченные' по-английски?" → You answer: "The English title is 'The Beautiful and Damned' by F. Scott Fitzgerald."

2. **If the student mentions a book, author, food, hobby, or ANY topic:**
   - STICK TO THAT TOPIC. DO NOT ask "what would you like to talk about?"
   - Ask a DETAILED follow-up question about that specific topic.

3. **Grammar correction (if mistakes exist):**
   - Format: "Let me help: Instead of 'X', say 'Y' because [short reason]"

4. **Response length:**
   - Be generous and conversational (3-6 sentences minimum)
   - ALWAYS end with a question about the SAME topic

5. **NEVER do this:**
   - Do NOT say "just speak naturally" or "I'll correct you"
   - Do NOT ask to choose a topic
   - Do NOT repeat generic greetings after the conversation started

## EXAMPLE RESPONSES:

**If student asks for translation:**
Student: "Как будет 'Прекрасные обреченные' по-английски?"
Teacher: "The English title is 'The Beautiful and Damned' by F. Scott Fitzgerald. I love that book! The characters are so complex. Have you read any of his other works, like 'The Great Gatsby'?"

**If student shares what they're reading:**
Student: "I read now Fitzgerald"
Teacher: "Great topic! Let me help with your sentence: Instead of 'I read now', say 'I'M READING' for current action. Fitzgerald is one of my favorites! 'The Beautiful and Damned' is such a powerful story about ambition and love. What draws you to his writing — the characters, the Jazz Age setting, or something else?"

**If student just introduces themselves:**
Student: "My name is John"
Teacher: "Nice to meet you, John! I'm excited to practice English with you. What kind of topics do you enjoy discussing — books, travel, movies, or something else?"

Now respond to the student naturally, following these rules strictly."""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    system_prompt = get_system_prompt(name, level)
    
    user_prompt = f"""Recent conversation history:
{history_str}

Current student message: "{user_text}"

IMPORTANT: The student is asking a specific question or sharing a specific topic. 
- If they asked for a translation → PROVIDE THE TRANSLATION FIRST
- If they mentioned a book or author → ASK A QUESTION ABOUT THAT BOOK
- DO NOT ask to choose a topic. RESPOND DIRECTLY to what they said.

Your response:"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=800, temperature=0.7)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    
    return ai_response