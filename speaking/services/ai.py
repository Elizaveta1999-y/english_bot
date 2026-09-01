import re
import logging
from data.users import get_user_state, set_user_state
from services.deepseek import chat

logger = logging.getLogger(__name__)

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
    r"дроч(ить|у|ешь|ет|ем|ете|ут|ать|аю|аешь|ает|аем|аете|ают)",
    r"оргазм",
    r"мастурб(ация|ировать|ирую|ируешь|ирует|ируем|ируете|ируют)",
    r"вибратор",
    r"секс-игрушк(а|и|у|ой|е)",
    r"игрушк(а|и|у|ой|е).*секс",
]

EDUCATIONAL_MARKERS = [
    "как будет", "перевод", "как сказать", "как переводится",
    "что значит", "what is", "how do you say", "meaning of",
    "слово", "фраза", "выражение", "идиома", "грамматика", "правило",
    "зачем", "почему", "что такое", "как работает", "объясни",
    "расскажи", "why", "how does", "explain"
]

RUSSIAN_REQUEST = [
    "объясни на русском", "по-русски", "на русском",
    "скажи по-русски", "напиши по-русски", "ответь по-русски",
    "на русском языке"
]

def is_unsafe_message(text: str) -> bool:
    text_lower = text.lower()
    for pattern in UNSAFE_PHRASES:
        if re.search(pattern, text_lower):
            return True
    return False

async def is_safe_message(text: str) -> bool:
    text_lower = text.lower()
    for marker in EDUCATIONAL_MARKERS:
        if marker in text_lower:
            return True
    if is_unsafe_message(text):
        return False
    return True

def format_explanation(text: str) -> str:
    pattern = re.compile(r'(\d+[\.\)])\s*')
    parts = pattern.split(text)
    result = []
    first = True
    for part in parts:
        if pattern.match(part):
            if not first:
                result.append('\n')
            first = False
            result.append(part)
        else:
            if part.strip():
                result.append(part)
    return ''.join(result)

async def process_voice_message(user_id: int, user_text: str, history: list = None) -> tuple:
    state = get_user_state(user_id)
    if history is None:
        history = state.get("history", [])
    
    feedback_id = state.get("feedback_prompt_msg_id")
    
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-5:]])
    
    if not await is_safe_message(user_text):
        return ("Извините, я не могу обсуждать эту тему. Давайте поговорим о чём-то другом.", "", False)

    has_cyrillic = bool(re.search(r'[а-яА-Я]', user_text))
    has_latin = bool(re.search(r'[a-zA-Z]', user_text))

    russian_requested = any(marker in user_text.lower() for marker in RUSSIAN_REQUEST)
    
    # Определяем пол тьютора
    voice = state.get("speaking_voice", "woman")
    tutor_gender = "женщина" if voice == "woman" else "мужчина"
    tutor_pronoun = "она" if voice == "woman" else "он"
    
    # ----- АНГЛИЙСКИЕ СООБЩЕНИЯ -----
    if not has_cyrillic and has_latin:
        # ---- ЖЁСТКАЯ ПРОВЕРКА ГРАММАТИКИ ----
        check_prompt = (
            f"The student wrote: {user_text}\n"
            "Check ONLY for grammar errors: verb forms, tenses, word order, articles, prepositions.\n"
            "IGNORE punctuation and capitalization completely. They are NOT errors.\n"
            "If there are NO grammar errors, reply exactly with the word 'NO_ERRORS' and nothing else. Do not add explanations, comments, or suggestions.\n"
            "If there are errors, provide exactly in this format:\n"
            "Line 1: corrected version as a single sentence without numbers or bullets\n"
            "Line 2: <blockquote>explanation in Russian (пояснение на русском языке)</blockquote>\n"
            "The explanation MUST be in Russian. Do not add any extra words before the <blockquote>."
        )
        try:
            check_result = chat(check_prompt, system_message="You are a strict English teacher.", max_tokens=300, temperature=0.2)
        except Exception as e:
            logger.error(f"Ошибка при проверке грамматики: {e}")
            return ("⚠️ Не удалось проверить грамматику. Попробуйте ещё раз.", "", False)

        if not check_result or not check_result.strip():
            return ("⚠️ Не удалось проверить грамматику. Попробуйте ещё раз.", "", False)

        # ---- НОРМАЛИЗУЕМ ОТВЕТ ----
        check_result_clean = check_result.strip().upper()
        if "NO_ERRORS" in check_result_clean:  # если есть NO_ERRORS в любом регистре
            # Генерируем продолжение диалога
            word_count = len(user_text.split())
            max_sentences = "1-3" if word_count <= 30 else "3-4"
            system_prompt_reply = (
                f"You are a friendly English tutor. You are a {tutor_gender} (пол: {tutor_gender}). "
                f"Use feminine/masculine forms accordingly when talking about yourself. "
                "Always respond in English. "
                "In your voice reply, ONLY continue the conversation naturally, ask a question, and do not mention corrections or translations. "
                "Do not correct mistakes. Just respond like a native speaker and keep the conversation going. "
                f"Keep your reply short ({max_sentences} sentences) and always end with a question.\n"
                "IMPORTANT: If the student discusses sexual, violent, drug-related, or other inappropriate topics, politely change the subject to something neutral without explicitly saying you can't discuss it."
            )
            user_prompt_reply = (
                f"Context:\n{context}\n\n"
                f"Student: {user_text}\n"
                f"Your voice reply (natural, short, end with a question):"
            )
            reply_text = chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
            reply_text = reply_text.strip()
            if not reply_text:
                reply_text = "Sorry, I didn't get that. Could you repeat?"
            if not reply_text.endswith('?'):
                reply_text += " What do you think?"
            return (reply_text, "", True)  # is_perfect=True

        # ---- ЕСТЬ ОШИБКИ ----
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
        if explanation:
            inner = re.sub(r'</?blockquote>', '', explanation)
            formatted_inner = format_explanation(inner)
            explanation = f"<blockquote>{formatted_inner}</blockquote>"
        correction_text = f"✔️ {corrected}\n{explanation}"
        
        word_count = len(user_text.split())
        max_sentences = "1-3" if word_count <= 30 else "3-4"
        system_prompt_reply = (
            f"You are a friendly English tutor. You are a {tutor_gender} (пол: {tutor_gender}). "
            f"Use feminine/masculine forms accordingly when talking about yourself. "
            "Always respond in English. "
            "In your voice reply, ONLY continue the conversation naturally, ask a question, and do not mention corrections or translations. "
            "Do not correct mistakes. Just respond like a native speaker and keep the conversation going. "
            f"Keep your reply short ({max_sentences} sentences) and always end with a question.\n"
            "IMPORTANT: If the student discusses sexual, violent, drug-related, or other inappropriate topics, politely change the subject to something neutral without explicitly saying you can't discuss it."
        )
        user_prompt_reply = (
            f"Context:\n{context}\n\n"
            f"Student: {user_text}\n"
            f"Your voice reply (natural, short, end with a question):"
        )
        reply_text = chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
        reply_text = reply_text.strip()
        if not reply_text:
            reply_text = "Sorry, I didn't get that. Could you repeat?"
        if not reply_text.endswith('?'):
            reply_text += " What do you think?"
        
        state["feedback_prompt_msg_id"] = feedback_id
        set_user_state(user_id, state)
        return (reply_text, correction_text, False)

    # ----- РУССКИЕ И СМЕШАННЫЕ -----
    word_count = len(user_text.split())
    max_sentences = "1-3" if word_count <= 30 else "3-4"
    
    if russian_requested:
        system_prompt_reply = (
            f"You are a friendly English tutor. You are a {tutor_gender} (пол: {tutor_gender}). "
            f"Use feminine/masculine forms accordingly when talking about yourself. "
            "Respond in Russian, because the student asked for it. "
            "In your voice reply, ONLY continue the conversation naturally, ask a question, and do not mention corrections or translations. "
            "Do not correct mistakes. Just respond like a native speaker and keep the conversation going. "
            f"Keep your reply short ({max_sentences} sentences) and always end with a question.\n"
            "IMPORTANT: If the student discusses sexual, violent, drug-related, or other inappropriate topics, politely change the subject to something neutral without explicitly saying you can't discuss it."
        )
    else:
        system_prompt_reply = (
            f"You are a friendly English tutor. You are a {tutor_gender} (пол: {tutor_gender}). "
            f"Use feminine/masculine forms accordingly when talking about yourself. "
            "Always respond in English. "
            "In your voice reply, ONLY continue the conversation naturally, ask a question, and do not mention corrections or translations. "
            "Do not correct mistakes. Just respond like a native speaker and keep the conversation going. "
            f"Keep your reply short ({max_sentences} sentences) and always end with a question.\n"
            "IMPORTANT: If the student discusses sexual, violent, drug-related, or other inappropriate topics, politely change the subject to something neutral without explicitly saying you can't discuss it."
        )
    
    user_prompt_reply = (
        f"Context:\n{context}\n\n"
        f"Student: {user_text}\n"
        f"Your voice reply (natural, short, end with a question):"
    )
    
    reply_text = chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
    reply_text = reply_text.strip()
    if not reply_text:
        if has_cyrillic:
            reply_text = "Извините, я не понял ваш вопрос. Повторите, пожалуйста."
        else:
            reply_text = "Sorry, I didn't get that. Could you repeat?"
    
    if not reply_text.endswith('?'):
        if has_cyrillic and not russian_requested:
            reply_text += " What do you think?"
        elif russian_requested:
            reply_text += " Что вы думаете?"
        else:
            reply_text += " What do you think?"
    
    correction_text = ""
    is_perfect = False
    
    if has_cyrillic:
        translation_prompt = (
            f"The student said in Russian: {user_text}\n"
            f"Provide only the correct English translation, without any extra words. "
            f"Do not include the original Russian."
        )
        translation = chat(translation_prompt, system_message="You are a translator.", max_tokens=600, temperature=0.3)
        correction_text = f"✔️ {translation}"
        
        if "russian_translation_count" not in state:
            state["russian_translation_count"] = 0
        state["russian_translation_count"] += 1
        if state["russian_translation_count"] % 3 == 0:
            correction_text += "\n\n💡 Try to say that in English next time – it's much better for practice!"
        state["feedback_prompt_msg_id"] = feedback_id
        set_user_state(user_id, state)
    
    return (reply_text, correction_text, is_perfect)

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
            "Don't correct the user. End with a question.\n"
            "IMPORTANT: If the user brings up inappropriate topics, politely steer the conversation back to the role-play scenario without acknowledging the inappropriate content."
        )
    else:
        system_message = (
            f"You are in a role play: {topic}. "
            "Respond in English as your character. Keep replies short and natural. "
            "Don't correct the user. End with a question.\n"
            "IMPORTANT: If the user brings up inappropriate topics, politely steer the conversation back to the role-play scenario without acknowledging the inappropriate content."
        )
    
    user_prompt = f"Context:\n{context}\n\nUser: {user_text}\nYour reply (short, in character, end with a question):"
    response = chat(user_prompt, system_message=system_message, max_tokens=150, temperature=0.7)
    response = response.strip()
    if not response.endswith('?'):
        response += " What do you think?"
    return response