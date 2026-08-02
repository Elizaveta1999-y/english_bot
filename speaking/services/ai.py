import re
from data.users import get_user_state
from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str) -> tuple:
    """
    Возвращает (reply_text, correction_text).
    - reply_text: только развитие беседы, без исправлений.
    - correction_text: исправления ошибок / перевод русского на английский (с зачёркиванием), или пустая строка.
    """
    state = get_user_state(user_id)
    history = state.get("history", [])
    
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-5:]])
    
    # Основной промт для развития беседы (без исправлений)
    system_prompt_reply = (
        "You are a friendly English tutor. Always respond in English. "
        "In your voice reply, ONLY continue the conversation naturally, ask a question, and do not mention corrections or translations. "
        "Do not correct mistakes, do not rephrase Russian. Just respond like a native speaker and keep the conversation going. "
        "Keep your reply short (1-3 sentences) and always end with a question."
    )
    
    user_prompt_reply = (
        f"Context:\n{context}\n\n"
        f"Student: {user_text}\n"
        f"Your voice reply (natural, short, end with a question):"
    )
    
    reply_text = chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
    reply_text = reply_text.strip()
    if not reply_text.endswith('?'):
        reply_text += " What do you think?"
    
    # Отдельный промт для исправлений/перевода (если нужно)
    correction_text = ""
    
    # Проверяем, есть ли русский язык
    if re.search(r'[а-яА-Я]', user_text):
        # Пользователь говорил по-русски – переводим его сообщение на английский
        translation_prompt = (
            f"The student said in Russian: {user_text}\n"
            f"Provide only the correct English translation, without any extra words, as a single sentence. "
            f"Do not include the original Russian."
        )
        correction_text = chat(translation_prompt, system_message="You are a translator.", max_tokens=100, temperature=0.3)
        correction_text = f"📝 Можно сказать так:\n{correction_text}"
    else:
        # Проверяем, есть ли грамматические ошибки в английском тексте
        check_prompt = (
            f"The student wrote: {user_text}\n"
            f"If there are any grammar mistakes, provide the corrected version and a brief explanation. "
            f"If there are no mistakes, reply with 'NO_ERRORS'."
        )
        check_result = chat(check_prompt, system_message="You are a strict English teacher.", max_tokens=100, temperature=0.3)
        if check_result.strip() != "NO_ERRORS" and len(check_result) > 3:
            correction_text = f"❌ Исправление:\n{check_result}"
    
    return reply_text, correction_text

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
            "Don't correct the user. End with a question."
        )
    else:
        system_message = (
            f"You are in a role play: {topic}. "
            "Respond in English as your character. Keep replies short and natural. "
            "Don't correct the user. End with a question."
        )
    
    user_prompt = f"Context:\n{context}\n\nUser: {user_text}\nYour reply (short, in character, end with a question):"
    response = chat(user_prompt, system_message=system_message, max_tokens=150, temperature=0.7)
    response = response.strip()
    if not response.endswith('?'):
        response += " What do you think?"
    return response

async def is_safe_message(text: str) -> bool:
    """
    Простая проверка на недопустимое содержание.
    """
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