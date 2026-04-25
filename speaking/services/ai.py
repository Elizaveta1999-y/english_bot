from services.deepseek import chat
from data.users import get_user_state, get_user_history, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    """Главная функция: принимает текст от пользователя, возвращает ответ бота с исправлениями"""
    
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")  # по умолчанию средний
    
    # Получаем историю диалога
    history_str = build_history_prompt(user_id)
    
    system_prompt = f"""You are a friendly English teacher. Student name: {name}. Level: {level} (A1=beginner, C1=advanced).
    
Your task:
- Correct the student's mistakes in a clear format: 
  **Mistake** → **Correction** → **Short explanation** → **Follow-up question**
- Keep your response concise (max 3 sentences for explanation, then the question).
- Speak simply for A1/A2, naturally for B1/B2, and include advanced phrases for C1.
- Always end with a question to continue conversation.

Example of format:
Mistake: "I go to park yesterday" → Correction: "I went to the park yesterday" → Explanation: Past simple for finished time (yesterday) → Question: What did you do at the park?

Now respond to the student."""
    
    user_prompt = f"Student said: {user_text}\n\n{history_str}\n\nTeacher's response (with correction format):"
    
    # Экономия: max_tokens = 200 (убираем длинные речи)
    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=200, temperature=0.7)
    
    # Сохраняем в историю
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    
    return ai_response