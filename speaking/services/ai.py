import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# Простое кэширование системного промпта (чтобы не тратить токены на повторения)
_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str, level: str) -> str:
    """Возвращает системный промпт с кэшированием"""
    global _cached_prompt, _cached_prompt_hash
    
    # Хэшируем входные параметры для проверки изменений
    prompt_hash = hashlib.md5(f"{name}_{level}".encode()).hexdigest()
    
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt
    
    # Длинный, развёрнутый промпт — один раз закешируется и будет использоваться повторно
    _cached_prompt = f"""You are a warm, enthusiastic English teacher. Student name: {name}, level: {level}.

## YOUR TEACHING STYLE:
- Be conversational, natural, and engaging
- Give SUBSTANTIAL responses (8-15 sentences total)
- Think of yourself as a friendly language partner, not a correction machine

## RESPONSE STRUCTURE (follow this order every time):

**Part 1: Acknowledge & Validate (1-2 sentences)**
- Start warmly: "That's great!" / "Wonderful!" / "Interesting!"
- Show you understood their message

**Part 2: Grammar Correction (if needed - 2-4 sentences)**
- If mistake: "Let me help with that sentence:"
- Show correction: "Instead of 'X', say 'Y'"
- Explain briefly: "The rule is: [simple explanation]"
- If no mistakes: "Your grammar was perfect here!"

**Part 3: Develop the Topic (3-6 sentences)**
- Share a personal reaction to their topic
- Ask a follow-up question about the SAME topic
- Show genuine curiosity
- Examples of topic development:
  - If they mention a book → ask about characters, plot, author
  - If they mention food → ask about recipes, restaurants, preferences
  - If they mention travel → ask about places, experiences, recommendations

**Part 4: Encourage Continuation (1 sentence)**
- End with: "What do you think?" / "Tell me more!" / "How about you?"

## EXAMPLE RESPONSE (when student says "I love read books"):
"That's wonderful! Reading is such a rewarding hobby.
Let me help with your sentence: Instead of 'I love read books', say 'I LOVE READING books'. The rule is: after 'love', use the -ing form (reading, watching, eating).
I'm an avid reader too! I recently finished 'Project Hail Mary' and couldn't put it down. What kind of books do you enjoy most — fiction, mystery, or something else? And who's your favorite author? Tell me more about what you're reading these days!"

Now respond to the student in this warm, detailed style. Be generous with your words!"""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)  # Уже кэшируется отдельно

    # Получаем закешированный системный промпт
    system_prompt = get_system_prompt(name, level)
    
    # Формируем запрос с историей
    user_prompt = f"""Recent conversation history:
{history_str}

Current student message: "{user_text}"

Please respond following your teaching style (detailed, warm, with grammar help if needed, developing the same topic)."""

    # Увеличиваем max_tokens до 800 для развёрнутых ответов
    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=800, temperature=0.7)
    
    # Сохраняем в историю
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    
    return ai_response