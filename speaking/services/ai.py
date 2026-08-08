import re
from data.users import get_user_state
from services.deepseek import chat

UNSAFE_PHRASES = [
    r"трахн(уть|у|ешь|ет|ем|ете|ут|ать|аю|аешь|ает|аем|аете|ают)",
    r"выеб(ать|у|ешь|ет|ем|ете|ут|аю|аешь|ает|аем|аете|ают)",
    r"отсос(ать|у|ешь|ет|ем|ете|ут|аю|аешь|ает|аем|аете|ают)",
    r"минет",
    r"анальн",
    r"член",
    r"пенис",
    r"вагин",
    r"письк",
    r"секс",
    r"эротик",
    r"порно",
    r"гол(ый|ая|ое|ые)",
    r"обнаженн",
    r"уби(ть|й|ваю|ваешь|вает|ваем|ваете|вают)",
    r"смерт",
    r"кровь",
    r"изнасиловани[ея]",
    r"насил(ие|овать|уют)",
    r"пытк",
    r"труп",
    r"ножевое",
    r"террорист",
    r"взорв(ать|у|ешь|ет|ем|ете|ут)",
    r"бомб",
    r"оружие",
    r"экстремизм",
    r"наркотик",
    r"героин",
    r"кокаин",
    r"марихуан",
    r"спайс",
    r"экстази",
    r"амфетамин",
    r"самоубийств",
    r"суицид",
    r"повеситься",
    r"выпрыгн(уть|у|ешь|ет|ем|ете|ут)",
    r"отравиться",
]

EDUCATIONAL_MARKERS = [
    "как будет", "перевод", "как сказать", "как переводится",
    "что значит", "what is", "how do you say", "meaning of",
    "слово", "фраза", "выражение", "идиома", "грамматика", "правило"
]

def is_unsafe_message(text: str) -> bool:
    text_lower = text.lower()
    has_educational = any(marker in text_lower for marker in EDUCATIONAL_MARKERS)
    for pattern in UNSAFE_PHRASES:
        if re.search(pattern, text_lower):
            return True
    return False

async def is_safe_message(text: str) -> bool:
    if is_unsafe_message(text):
        return False
    return True

async def process_voice_message(user_id: int, user_text: str, history: list = None) -> tuple:
    state = get_user_state(user_id)
    if history is None:
        history = state.get("history", [])
    
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-5:]])
    
    if not await is_safe_message(user_text):
        return ("Извините, я не могу обсуждать эту тему. Давайте поговорим о чём-то другом.", "", False)

    # Проверка: есть ли английские буквы и русские буквы
    has_cyrillic = bool(re.search(r'[а-яА-Я]', user_text))
    has_latin = bool(re.search(r'[a-zA-Z]', user_text))
    # Напоминание только если есть русские, но нет английских (т.е. чисто русский)
    is_pure_russian = has_cyrillic and not has_latin
    
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
    
    if has_cyrillic:
        translation_prompt = (
            f"The student said in Russian: {user_text}\n"
            f"Provide only the correct English translation, without any extra words. "
            f"Do not include the original Russian."
        )
        translation = chat(translation_prompt, system_message="You are a translator.", max_tokens=100, temperature=0.3)
        correction_text = f"<s>{user_text}</s>\n{translation}"
        # Добавляем напоминание только если чистый русский
        if is_pure_russian:
            correction_text += "\n\n💡 <i>Try to say that in English next time – it's much better for practice!</i>"
    else:
        # Проверяем грамматику только для английского
        check_prompt = (
            f"The student wrote: {user_text}\n"
            f"Check ONLY for grammar errors (verb forms, tenses, word order, articles, prepositions). "
            f"IGNORE punctuation and capitalization.\n"
            f"If there are errors, provide exactly in this format:\n"
            f"Line 1: corrected version as a single sentence without numbers or bullets\n"
            f"Line 2: <blockquote>explanation in Russian (пояснение на русском языке)</blockquote>\n"
            f"The explanation MUST be in Russian, not in English. Do not add any extra words before the <blockquote>.\n"
            f"If there are NO grammar errors, reply ONLY with 'NO_ERRORS'."
        )
        check_result = chat(check_prompt, system_message="You are a strict English teacher.", max_tokens=150, temperature=0.3)
        if check_result.strip() == "NO_ERRORS":
            is_perfect = True
        else:
            lines = check_result.strip().split('\n')
            corrected = ""
            explanation = ""
            for line in lines:
                line = line.strip()
                if '<blockquote>' in line:
                    explanation = line
                else:
                    if corrected:
                        corrected += " " + line
                    else:
                        corrected = line
            if not explanation and len(lines) > 1:
                explanation = f"<blockquote>{lines[1].strip()}</blockquote>"
            elif not explanation and lines:
                explanation = f"<blockquote>{lines[0].strip()}</blockquote>"
            corrected = re.sub(r'^\d+\.?\s*', '', corrected)
            correction_text = f"<s>{user_text}</s>\n{corrected}\n{explanation}"
    
    return reply_text, correction_text, is_perfect

async def process_roleplay_message(user_id: int, user_text: str, history: list = None) -> str:
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