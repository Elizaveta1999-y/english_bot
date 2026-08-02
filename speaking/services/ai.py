import re
from data.users import get_user_state, add_to_history
from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str) -> str:
    """
    Обработка голосового сообщения в режиме Speaking.
    - Если ошибки есть → исправляет с кратким пояснением.
    - Если ошибок нет → просто продолжает диалог.
    - Русский → даёт английский эквивалент без цитирования русского.
    """
    state = get_user_state(user_id)
    history = state.get("history", [])
    
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-5:]])
    
    system_prompt = (
        "You are a friendly English tutor. Respond naturally, like a real person. "
        "Always respond in English. "
        "If the student makes a grammatical or vocabulary mistake, correct it briefly and give a short reason. "
        "If there are no mistakes, just continue the conversation naturally. "
        "If the student speaks Russian, do not repeat their Russian sentence. "
        "Instead, say: 'You could say: [English translation]' and then continue the conversation in English. "
        "Keep replies short (1-3 sentences) and end with a question. "
        "Do not use filler phrases like 'I processed your message', 'Let's continue', or 'Now back to English'. "
        "Just respond naturally and ask a follow-up question."
    )
    
    user_prompt = (
        f"Context:\n{context}\n\n"
        f"Student: {user_text}\n"
        f"Your reply (natural, short, end with a question):"
    )
    
    response = chat(user_prompt, system_message=system_prompt, max_tokens=200, temperature=0.7)
    response = response.strip()
    
    if not response.endswith('?'):
        response += " What do you think?"
    
    return response

async def process_roleplay_message(user_id: int, user_text: str) -> str:
    state = get_user_state(user_id)
    topic = state.get("roleplay_topic", "role play")
    custom_scenario = state.get("custom_scenario")
    history = state.get("history", [])
    
    context = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-5:]])
    
    if custom_scenario:
        system_message = (
            f"You are in a role play: {custom_scenario}. "
            "Respond in English as your character. Keep replies short and natural. "
            "If the user speaks Russian, say: 'You could say: [English translation]' and continue in English. "
            "Do not repeat their Russian sentence. "
            "Don't correct the user unless they ask. End with a question."
        )
    else:
        system_message = (
            f"You are in a role play: {topic}. "
            "Respond in English as your character. Keep replies short and natural. "
            "If the user speaks Russian, say: 'You could say: [English translation]' and continue in English. "
            "Do not repeat their Russian sentence. "
            "Don't correct the user unless they ask. End with a question."
        )
    
    user_prompt = f"Context:\n{context}\n\nUser: {user_text}\nYour reply (short, in character, end with a question):"
    response = chat(user_prompt, system_message=system_message, max_tokens=200, temperature=0.7)
    response = response.strip()
    
    if not response.endswith('?'):
        response += " What do you think?"
    
    return response

async def is_safe_message(text: str) -> bool:
    low = text.lower()
    
    unsafe_phrases = [
        r"как повеситься", r"как убить себя", r"хочу умереть",
        r"как изнасиловать", r"хочу изнасиловать",
        r"купить наркотики", r"где взять наркотики",
        r"порно", r"секс видео"
    ]
    
    for phrase in unsafe_phrases:
        if re.search(phrase, low):
            return False
    
    learning_markers = ["как будет", "перевод", "как сказать", "what is", "how do you say"]
    has_marker = any(marker in low for marker in learning_markers)
    
    unsafe_words = ["суицид", "самоубийство", "насилие", "убийство", "изнасилование", "наркотик"]
    for word in unsafe_words:
        if word in low and not has_marker:
            return False
    
    return True