from data.users import get_user_history

def build_history_prompt(user_id: int) -> str:
    """Возвращает последние 4 пары сообщений для контекста"""
    history = get_user_history(user_id)
    if not history:
        return ""
    
    # Берём последние 8 сообщений (4 пары)
    recent = history[-8:] if len(history) > 8 else history
    
    lines = ["Previous conversation:"]
    for msg in recent:
        role = "Student" if msg.get("role") == "user" else "Teacher"
        
        # Пробуем получить текст из поля 'text' или 'content'
        text = msg.get("text", "")
        if not text:
            text = msg.get("content", "")
        
        lines.append(f"{role}: {text[:200]}")
    
    return "\n".join(lines)