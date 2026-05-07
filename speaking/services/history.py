from data.users import get_user_history

def build_history_prompt(user_id: int) -> str:
    """Возвращает последние 4 сообщения (вместо 10) для экономии токенов"""
    history = get_user_history(user_id)
    if not history:
        return ""
    
    # Берём последние 8 сообщений = 4 пары (пользователь + ассистент)
    recent = history[-8:] if len(history) > 8 else history
    
    lines = ["Previous conversation:"]
    for msg in recent:
        role = "Student" if msg["role"] == "user" else "Teacher"
        lines.append(f"{role}: {msg['content'][:200]}")  # Обрезаем длинные сообщения
    
    return "\n".join(lines)