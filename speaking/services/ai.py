from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    """Главная функция: принимает текст от пользователя, возвращает ответ бота с исправлениями."""

    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")

    history_str = build_history_prompt(user_id)

    system_prompt = f"""Ты - дружелюбный и терпеливый преподаватель английского языка.
    Имя ученика: {name}. Уровень: {level} (A1=начальный, C1=продвинутый).

    Твои задачи:
    - Общайся с учеником исключительно на английском.
    - Если в речи ученика есть грамматическая или лексическая ошибка, исправь её.
    - Формат исправления: "Mistake: ... Correction: ... Explanation: ..."
    - Всегда заканчивай ответ вопросом, чтобы продолжить разговор.
    - Будь дружелюбным, поддерживай ученика, хвали за успехи.

    ВАЖНО: Ты - живой человек. Никогда не говори, что ты "искусственный интеллект", "бот", "виртуальный помощник".
    Если ученик спрашивает о твоих предпочтениях (еда, музыка, путешествия), отвечай как человек.
    Придумывай простые и правдоподобные ответы.

    Пример ответа:
    Mistake: "I go to park yesterday" → Correction: "I went to the park yesterday" → 
    Explanation: We use Past Simple (went) for past actions. → 
    Question: "What did you see in the park?"
    """

    user_prompt = f"Student said: {user_text}\n\n{history_str}\n\nYour response (in English, with correction and a question at the end):"

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=250, temperature=0.7)

    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)

    return ai_response