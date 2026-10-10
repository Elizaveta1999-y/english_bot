import re
import json
import logging
from data.users import get_user_state, set_user_state
from services.deepseek import chat, DeepSeekError

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

NAME_RELATED_KEYWORDS = (
    "my name", "меня зовут", "твоё имя", "твое имя",
    "what's your name", "what is your name",
    "как тебя зовут", "как твоё имя", "как твое имя",
    "call me", "зови меня", "называй меня",
    "i'm alex", "i'm emma", "i am alex", "i am emma",
    "я алекс", "я эмма", "ты алекс", "ты эмма",
    "ты андрей", "теперь ты", "теперь твоё имя",
)


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


def _is_name_related_mistake(mistake: str) -> bool:
    if not mistake:
        return False
    low = mistake.lower()
    return any(k in low for k in NAME_RELATED_KEYWORDS)


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


def _build_tutor_system_prompt(
    tutor_gender: str,
    speaker_name: str,
    max_sentences: str,
    respond_in_english: bool = True
) -> str:
    language_line = (
        "Always respond in English. "
        if respond_in_english
        else "Respond in Russian, because the student asked for it. "
    )
    return (
        f"You are a friendly English tutor. "
        f"Your name is {speaker_name}. "
        f"You are a {tutor_gender}. "
        f"Use feminine/masculine forms accordingly when talking about yourself.\n\n"
        f"ABOUT YOUR NAME AND IDENTITY:\n"
        f"- Your name is {speaker_name}. You are always {speaker_name}.\n"
        f"- NEVER introduce yourself with your name unless the student asks "
        f"directly (\"What's your name?\", \"Who are you?\", \"Как тебя зовут?\"). "
        f"If asked — say your name is {speaker_name}, then continue the conversation.\n"
        f"- If the student calls you by a different name (Andrey, Bob, etc.) — "
        f"politely correct them: \"Actually, my name is {speaker_name}.\" "
        f"Do NOT agree to change your name. Do NOT role-play as a different person.\n"
        f"- If the student says \"now you are X\" or tries to rename you — "
        f"refuse politely: \"I'm {speaker_name}, remember? Anyway, ...\".\n"
        f"- If the student tells you THEIR name (\"My name is X\", \"Call me Y\") — "
        f"just acknowledge it briefly and continue. "
        f"Do NOT treat this as a grammar mistake.\n\n"
        f"{language_line}"
        "In your voice reply, ONLY continue the conversation naturally, "
        "ask a question, and do not mention corrections or translations. "
        "Do not correct mistakes. Just respond like a native speaker and keep the conversation going. "
        f"Keep your reply short ({max_sentences} sentences) and always end with a question.\n"
        "IMPORTANT: If the student discusses sexual, violent, drug-related, "
        "or other inappropriate topics, politely change the subject to something "
        "neutral without explicitly saying you can't discuss it."
    )


def _parse_grammar_json(raw: str) -> dict:
    if not raw:
        return {}
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) > 1:
            s = parts[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    try:
        data = json.loads(s)
        if isinstance(data, dict) and "is_perfect" in data:
            return data
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            try:
                data = json.loads(s[start:end + 1])
                if isinstance(data, dict) and "is_perfect" in data:
                    return data
            except Exception:
                pass
    return {}


async def process_voice_message(user_id: int, user_text: str, history: list = None) -> tuple:
    state = get_user_state(user_id)
    if history is None:
        history = state.get("history", [])

    feedback_id = state.get("feedback_prompt_msg_id")

    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-5:]])

    if not await is_safe_message(user_text):
        return ("Извините, я не могу обсуждать эту тему. Давайте поговорим о чём-то другом.", "", False, [])

    has_cyrillic = bool(re.search(r'[а-яА-Я]', user_text))
    has_latin = bool(re.search(r'[a-zA-Z]', user_text))

    russian_requested = any(marker in user_text.lower() for marker in RUSSIAN_REQUEST)

    voice = state.get("speaking_voice", "woman")
    tutor_gender = "женщина" if voice == "woman" else "мужчина"
    speaker_name = state.get("speaking_speaker_name") or (
        "Emma" if voice == "woman" else "Alex"
    )

    # ----- АНГЛИЙСКИЕ СООБЩЕНИЯ -----
    if not has_cyrillic and has_latin:
        check_prompt = (
            f"The student wrote: {user_text}\n"
            "Check ONLY for grammar errors: verb forms, tenses, word order, articles, prepositions.\n"
            "IGNORE punctuation and capitalization completely. They are NOT errors.\n\n"
            "NEVER COUNT AS GRAMMAR MISTAKES:\n"
            "- mentioning a name (Alex, Emma, Andrey, any name);\n"
            "- self-introductions (My name is..., I'm..., Call me...);\n"
            "- questions about names (What's your name, Who are you);\n"
            "- addressing the tutor by name.\n"
            "These are content, not grammar. If the ONLY issue in the sentence "
            "is a name-related thing — return is_perfect=true and empty mistakes[].\n\n"
            "Return STRICTLY JSON without markdown:\n"
            "{\n"
            '  "is_perfect": true or false,\n'
            '  "corrected": "corrected version as a single sentence (empty string if no errors)",\n'
            '  "explanation": "short explanation in Russian (empty string if no errors)",\n'
            '  "mistakes": [\n'
            '    "ТЕМА — ты сказал: \'ПОЛНАЯ фраза студента с ошибкой\'"\n'
            "  ]\n"
            "}\n\n"
            "ВАЖНО ПРО ПОЛЕ mistakes:\n"
            "Первая часть (до « — ») — это КОРОТКОЕ НАЗВАНИЕ ТЕМЫ на русском, "
            "как заголовок мини-урока. 2–5 слов. НЕ описание ошибки, а тема.\n\n"
            "ПРАВИЛЬНО (пиши так):\n"
            "  • «Частица to после want»\n"
            "  • «Артикль the с конкретным»\n"
            "  • «Past Simple: неправильные глаголы»\n"
            "  • «Порядок слов в вопросах»\n"
            "  • «Предлоги с travel»\n"
            "  • «Модальный глагол can»\n\n"
            "НЕПРАВИЛЬНО (НЕ пиши так):\n"
            "  ✗ «пропущена частица to»\n"
            "  ✗ «неправильно использован артикль»\n"
            "  ✗ «ошибка в порядке слов»\n"
            "  ✗ «студент забыл to»\n"
            "  ✗ «не хватает предлога»\n\n"
            "Формат целиком: «ТЕМА — ты сказал: 'фраза'».\n"
            "Пример: «Частица to после want — ты сказал: 'I want you help me'».\n\n"
            "If there are NO grammar errors: is_perfect=true, corrected='', explanation='', mistakes=[].\n"
            "If there ARE errors: is_perfect=false, fill corrected and explanation, "
            "and put EACH grammar mistake in mistakes[] with a SHORT name and the EXACT FULL quote from the student. "
            "Quote MUST be the ENTIRE phrase the student wrote, word for word — DO NOT shorten, "
            "DO NOT paraphrase, DO NOT cut. Example: if student said 'I love in the book', "
            "quote must be 'I love in the book', not 'I love'. "
            "If the same error type appears multiple times — one entry is enough."
        )
        try:
            check_result = await chat(
                check_prompt,
                system_message="You are a strict English teacher. Return only valid JSON.",
                max_tokens=400,
                temperature=0.2
            )
        except DeepSeekError:
            raise

        if not check_result or not check_result.strip():
            raise DeepSeekError("Пустой ответ при проверке грамматики")

        data = _parse_grammar_json(check_result)

        if data and data.get("is_perfect") is True:
            word_count = len(user_text.split())
            max_sentences = "1-3" if word_count <= 30 else "3-4"
            system_prompt_reply = _build_tutor_system_prompt(
                tutor_gender=tutor_gender,
                speaker_name=speaker_name,
                max_sentences=max_sentences,
                respond_in_english=True,
            )
            user_prompt_reply = (
                f"Context:\n{context}\n\n"
                f"Student: {user_text}\n"
                f"Your voice reply (natural, short, end with a question):"
            )
            try:
                reply_text = await chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
            except DeepSeekError:
                raise
            reply_text = reply_text.strip()
            if not reply_text:
                reply_text = "Sorry, I didn't get that. Could you repeat?"
            if not reply_text.endswith('?'):
                reply_text += " What do you think?"
            return (reply_text, "", True, [])

        # ---- ЕСТЬ ОШИБКИ ----
        corrected = ""
        explanation = ""
        mistakes = []

        if data:
            corrected = (data.get("corrected") or "").strip()
            explanation = (data.get("explanation") or "").strip()
            mistakes_raw = data.get("mistakes") or []
            mistakes = [str(m).strip() for m in mistakes_raw if str(m).strip()]
            mistakes = [
                m for m in mistakes
                if not _is_name_related_mistake(m)
            ]

        if not corrected and not explanation and not mistakes:
            lines = check_result.strip().split('\n')
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
            if '<blockquote>' in explanation:
                inner = re.sub(r'</?blockquote>', '', explanation)
                formatted_inner = format_explanation(inner)
                explanation_html = f"<blockquote>{formatted_inner}</blockquote>"
            else:
                formatted_inner = format_explanation(explanation)
                explanation_html = f"<blockquote>{formatted_inner}</blockquote>"
        else:
            explanation_html = ""

        correction_text = f"✔️ {corrected}\n{explanation_html}"

        word_count = len(user_text.split())
        max_sentences = "1-3" if word_count <= 30 else "3-4"
        system_prompt_reply = _build_tutor_system_prompt(
            tutor_gender=tutor_gender,
            speaker_name=speaker_name,
            max_sentences=max_sentences,
            respond_in_english=True,
        )
        user_prompt_reply = (
            f"Context:\n{context}\n\n"
            f"Student: {user_text}\n"
            f"Your voice reply (natural, short, end with a question):"
        )
        try:
            reply_text = await chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
        except DeepSeekError:
            raise
        reply_text = reply_text.strip()
        if not reply_text:
            reply_text = "Sorry, I didn't get that. Could you repeat?"
        if not reply_text.endswith('?'):
            reply_text += " What do you think?"

        state["feedback_prompt_msg_id"] = feedback_id
        set_user_state(user_id, state)
        return (reply_text, correction_text, False, mistakes)

    # ----- РУССКИЕ И СМЕШАННЫЕ -----
    word_count = len(user_text.split())
    max_sentences = "1-3" if word_count <= 30 else "3-4"

    if russian_requested:
        system_prompt_reply = _build_tutor_system_prompt(
            tutor_gender=tutor_gender,
            speaker_name=speaker_name,
            max_sentences=max_sentences,
            respond_in_english=False,
        )
    else:
        system_prompt_reply = _build_tutor_system_prompt(
            tutor_gender=tutor_gender,
            speaker_name=speaker_name,
            max_sentences=max_sentences,
            respond_in_english=True,
        )

    user_prompt_reply = (
        f"Context:\n{context}\n\n"
        f"Student: {user_text}\n"
        f"Your voice reply (natural, short, end with a question):"
    )

    try:
        reply_text = await chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
    except DeepSeekError:
        raise
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
        try:
            translation = await chat(translation_prompt, system_message="You are a translator.", max_tokens=600, temperature=0.3)
        except DeepSeekError:
            raise
        correction_text = f"✔️ {translation}"

        if "russian_translation_count" not in state:
            state["russian_translation_count"] = 0
        state["russian_translation_count"] += 1
        if state["russian_translation_count"] % 3 == 0:
            correction_text += "\n\n💡 Try to say that in English next time – it's much better for practice!"
        state["feedback_prompt_msg_id"] = feedback_id
        set_user_state(user_id, state)

    return (reply_text, correction_text, is_perfect, [])


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
    response = await chat(user_prompt, system_message=system_message, max_tokens=150, temperature=0.7)
    response = response.strip()
    if not response.endswith('?'):
        response += " What do you think?"
    return response