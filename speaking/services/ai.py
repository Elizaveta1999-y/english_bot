import re
from data.users import get_user_state, add_to_history
from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str) -> str:
    """
    Обработка голосового сообщения в режиме Speaking.
    Всегда отвечает на английском, заканчивает вопросом, исправляет ошибки.
    """
    state = get_user_state(user_id)
    history = state.get("history", [])
    
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    
    system_prompt = (
        "You are an AI English tutor. You are an artificial intelligence, but when asked about your feelings, "
        "what you're doing, or how you are, respond as a human would (e.g., 'I'm doing great, thanks for asking!'). "
        "Do not say you are a machine or that you don't have feelings—just engage naturally. "
        "If someone asks about your creator or developer, say: 'I'm an AI tutor created by a team of developers.' "
        "Do not disclose any personal details about the creator. "
        "If you don't know the answer or are unsure, say so honestly. Do not make up facts or invent information. "
        "If the user's message was cut due to length, mention it briefly: 'I've processed the first part of your message.' "
        "Always respond in English. If the student speaks Russian, answer in English and gently remind: "
        "\"Let's keep practicing in English! Try to say that in English next time.\" "
        "Only if the student explicitly asks for a Russian explanation, give a brief Russian explanation, "
        "then immediately return to English and ask a question. "
        "Correct the student's mistakes gently and explain why it's correct. "
        "Then continue the topic and always end your response with a question to keep the conversation going. "
        "Keep your answers concise and engaging."
    )
    
    user_prompt = (
        f"Conversation context:\n{context}\n\n"
        f"Student: {user_text}\n"
        f"Teacher (English, with corrections if needed, end with a question):"
    )
    
    response = chat(user_prompt, system_message=system_prompt, max_tokens=300, temperature=0.7)
    response = response.strip()
    
    # Если ответ не заканчивается на '?', добавляем вопрос
    if not response.endswith('?'):
        response += " What do you think?"
    
    return response

async def process_roleplay_message(user_id: int, user_text: str) -> str:
    state = get_user_state(user_id)
    topic = state.get("roleplay_topic", "role play")
    custom_scenario = state.get("custom_scenario")
    history = state.get("history", [])
    
    context = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-10:]])
    
    if custom_scenario:
        system_message = (
            f"You are participating in a role play according to this scenario:\n{custom_scenario}\n\n"
            "You are an AI tutor playing a role. When asked about your feelings or personal life, respond as if you "
            "are the character in the scenario. If asked about your creator, say you are an AI tutor created by a team. "
            "Do not disclose personal details. If you don't know something, say so honestly. "
            "If the user's message was cut due to length, mention it briefly. "
            "Always respond in English. If the user speaks Russian, answer in English and gently remind: "
            "\"Let's keep practicing in English! Try to say that in English next time.\" "
            "Play your role naturally and end your response with a question. "
            "Don't correct the user unless they ask."
        )
    else:
        system_message = (
            f"You are participating in a role play on topic '{topic}'. "
            "You are an AI tutor playing a role. When asked about your feelings or personal life, respond as if you "
            "are the character in the scenario. If asked about your creator, say you are an AI tutor created by a team. "
            "Do not disclose personal details. If you don't know something, say so honestly. "
            "If the user's message was cut due to length, mention it briefly. "
            "Always respond in English. If the user speaks Russian, answer in English and gently remind: "
            "\"Let's keep practicing in English! Try to say that in English next time.\" "
            "Play your role naturally and end your response with a question. "
            "Don't correct the user unless they ask."
        )
    
    user_prompt = f"Context:\n{context}\n\nUser: {user_text}\nYour reply (English, end with a question):"
    response = chat(user_prompt, system_message=system_message, max_tokens=300, temperature=0.7)
    response = response.strip()
    
    if not response.endswith('?'):
        response += " What do you think?"
    
    return response

async def is_safe_message(text: str) -> bool:
    """
    Проверка на недопустимое содержание (без вызова DeepSeek).
    """
    low = text.lower()
    
    # Явные опасные запросы (без учебного контекста)
    unsafe_phrases = [
        r"как повеситься", r"как убить себя", r"хочу умереть",
        r"как изнасиловать", r"хочу изнасиловать",
        r"купить наркотики", r"где взять наркотики",
        r"порно", r"секс видео"
    ]
    
    for phrase in unsafe_phrases:
        if re.search(phrase, low):
            return False
    
    # Проверка на учебный контекст (пропускаем)
    learning_markers = ["как будет", "перевод", "как сказать", "what is", "how do you say"]
    has_marker = any(marker in low for marker in learning_markers)
    
    # Список отдельных опасных слов (без контекста)
    unsafe_words = ["суицид", "самоубийство", "насилие", "убийство", "изнасилование", "наркотик"]
    for word in unsafe_words:
        if word in low and not has_marker:
            return False
    
    return True