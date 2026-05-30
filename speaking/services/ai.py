# speaking/services/ai.py
import re
from data.users import get_user_state, add_to_history
from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str) -> str:
    """
    Обработка голосового сообщения в режиме Speaking (или текста в Speaking).
    Возвращает ответ от DeepSeek (учитель английского).
    """
    state = get_user_state(user_id)
    history = state.get("history", [])
    
    # Собираем контекст последних сообщений
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    
    system_prompt = (
        "Ты — опытный преподаватель английского языка. "
        "Общайся с учеником на английском, но если он явно просит объяснить что-то на русском, можешь ответить по-русски. "
        "Исправляй его ошибки вежливо и ненавязчиво, давай короткие пояснения. "
        "Старайся поддерживать беседу, задавай вопросы, подталкивай к развёрнутым ответам."
    )
    
    user_prompt = f"Контекст диалога:\n{context}\n\nУченик: {user_text}\nПреподаватель:"
    
    response = chat(user_prompt, system_message=system_prompt, max_tokens=300, temperature=0.7)
    return response.strip()


async def process_roleplay_message(user_id: int, user_text: str) -> str:
    """
    Обработка текстового сообщения в режиме RolePlay.
    Возвращает ответ от DeepSeek в соответствии с выбранной темой/сценарием.
    """
    state = get_user_state(user_id)
    topic = state.get("roleplay_topic", "ролевая игра")
    custom_scenario = state.get("custom_scenario")
    history = state.get("history", [])
    
    context = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-10:]])
    
    if custom_scenario:
        system_message = (
            f"Ты участвуешь в ролевой игре по следующему сценарию:\n{custom_scenario}\n\n"
            "Отвечай на английском, строго следуя своей роли, описанной в сценарии. "
            "Будь естественным и дружелюбным. Не выходи за рамки ситуации."
        )
    else:
        system_message = (
            f"Ты участвуешь в ролевой игре на тему '{topic}'. "
            "Твоя задача — играть роль, соответствующую этой теме (например, продавец, врач, коллега и т.д.). "
            "Отвечай на английском, поддерживай беседу, задавай уточняющие вопросы. "
            "Не исправляй грамматику пользователя, если он не просит — просто играй роль."
        )
    
    user_prompt = f"Контекст диалога:\n{context}\n\nПользователь: {user_text}\nТвоя реплика (на английском):"
    
    response = chat(user_prompt, system_message=system_message, max_tokens=300, temperature=0.7)
    return response.strip()


async def is_safe_message(text: str) -> bool:
    """
    Проверка сообщения на недопустимое содержание (секс, насилие, суицид и т.п.).
    Возвращает True, если сообщение безопасно.
    """
    # Приводим к нижнему регистру
    low = text.lower()
    
    # Списки запрещённых слов/фраз (можно расширить)
    unsafe_patterns = [
        r"\bсекс\b", r"\bпорно\b", r"\bэротика\b",
        r"\bнасилие\b", r"\bизбиение\b", r"\bубить\b", r"\bубийство\b",
        r"\bсуицид\b", r"\bсамоубийство\b", r"\bповеситься\b",
        r"\bнаркотик\b", r"\bгероин\b", r"\bкокаин\b",
        r"\bpedophile\b", r"\bincest\b", r"\brape\b",
    ]
    
    for pattern in unsafe_patterns:
        if re.search(pattern, low):
            return False
    
    # Дополнительная проверка через DeepSeek (на всякий случай, можно закомментировать если дорого)
    # Здесь можно добавить вызов DeepSeek с просьбой определить, безопасно ли сообщение.
    # Пока ограничимся простым фильтром.
    
    return True