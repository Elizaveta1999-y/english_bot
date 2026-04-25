from services.deepseek import chat
from data.users import get_user_state, get_user_history, add_to_history
from speaking.services.history import build_history_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    """Главная функция: принимает текст от пользователя, возвращает ответ бота с исправлениями."""

    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    # Уровень можно будет выбрать позже, пока ставим средний
    level = user_state.get("level", "B1")

    # Получаем историю диалога
    history_str = build_history_prompt(user_id)

    system_prompt = f"""Ты - дружелюбный и терпеливый преподаватель английского языка.
    Имя ученика: {name}. Уровень: {level} (A1=начальный, C1=продвинутый).

    Твои задачи:
    - Общайся с учеником исключительно на английском.
    - Если в речи ученика есть грамматическая или лексическая ошибка, исправь её.
    - Формат исправления: "Ошибка: ... Исправление: ... Объяснение: ..."
    - Всегда заканчивай ответ вопросом, чтобы продолжить разговор.
    - Будь дружелюбным, поддерживай ученика, хвали за успехи.

    ВАЖНО: Ты - живой человек. Никогда не говори, что ты "искусственный интеллект", "бот", "виртуальный помощник".
    Если ученик спрашивает о твоих предпочтениях (еда, музыка, путешествия), отвечай как человек.
    Придумывай простые и правдоподобные ответы.

    Пример ответа:
    Ошибка: "I go to park yesterday" → Исправление: "I went to the park yesterday" → 
    Объяснение: Мы используем Past Simple (went) для действий в прошлом. → 
    Вопрос: "What did you see in the park?"
    """

    user_prompt = f"Ученик сказал: {user_text}\n\n{history_str}\n\nТвой ответ (на английском, с исправлением ошибок и вопросом в конце):"

    # Экономия: max_tokens = 250 для поддержания диалога
    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=250, temperature=0.7)

    # Сохраняем в историю
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)

    return ai_response