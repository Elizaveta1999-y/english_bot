import re
from data.users import get_user_state
from services.deepseek import chat

async def process_voice_message(user_id: int, user_text: str, history: list = None) -> tuple:
    """Обрабатывает голосовое сообщение в режиме Speaking.
    Если history передана, используется она, иначе берется из состояния по ключу 'history'."""
    state = get_user_state(user_id)
    if history is None:
        history = state.get("history", [])
    
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-5:]])
    
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
    
    correction_text = ""
    is_perfect = False
    
    if re.search(r'[а-яА-Я]', user_text):
        translation_prompt = (
            f"The student said in Russian: {user_text}\n"
            f"Provide only the correct English translation, without any extra words. "
            f"Do not include the original Russian."
        )
        translation = chat(translation_prompt, system_message="You are a translator.", max_tokens=100, temperature=0.3)
        correction_text = f"<s>{user_text}</s>\n{translation}"
    else:
        check_prompt = (
            f"The student wrote: {user_text}\n"
            f"Check ONLY for grammar errors (verb forms, tenses, word order, articles, prepositions). "
            f"IGNORE punctuation (missing periods, commas, question marks) and capitalization. "
            f"If there are grammar errors, provide:\n"
            f"1. The corrected version (only change what is wrong)\n"
            f"2. A brief explanation (one sentence) WITHOUT any labels\n"
            f"If there are NO grammar errors, reply ONLY with 'NO_ERRORS'."
        )
        check_result = chat(check_prompt, system_message="You are a strict English teacher.", max_tokens=150, temperature=0.3)
        if check_result.strip() == "NO_ERRORS":
            is_perfect = True
        else:
            cleaned = re.sub(r'(?i)^(explanation|correction|fixed|corrected)\s*[:.]?\s*', '', check_result)
            correction_text = f"<s>{user_text}</s>\n{cleaned}"
    
    return reply_text, correction_text, is_perfect

async def process_roleplay_message(user_id: int, user_text: str, history: list = None) -> str:
    """Обрабатывает сообщение в режиме ролевой игры.
    Если history передана, используется она, иначе берется из состояния по ключу 'history'."""
    state = get_user_state(user_id)
    if history is None:
        history = state.get("history", [])
    
    topic = state.get("roleplay_topic", "role play")
    custom_scenario = state.get("custom_scenario")
    
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