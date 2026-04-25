from data.users import get_user_history

def build_history_prompt(user_id: int) -> str:
    """Возвращает строку с последними 5–10 сообщениями диалога"""
    history = get_user_history(user_id)
    if not history:
        return ""
    
    lines = ["Previous conversation:"]
    for msg in history[-6:]:  # последние 6 сообщений (3 пары)
        lines.append(f"{msg['role'].capitalize()}: {msg['content']}")
    return "\n".join(lines)