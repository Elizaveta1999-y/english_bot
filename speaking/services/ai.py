import re
import logging
from data.users import get_user_state, set_user_state
from services.deepseek import chat

logger = logging.getLogger(__name__)

UNSAFE_PHRASES = [
    # ... (без изменений, опускаю для краткости, но он должен быть полным)
]

EDUCATIONAL_MARKERS = [
    # ...
]

RUSSIAN_REQUEST = [
    # ...
]

def is_unsafe_message(text: str) -> bool:
    # ...

async def is_safe_message(text: str) -> bool:
    # ...

def format_explanation(text: str) -> str:
    # ...

async def process_voice_message(user_id: int, user_text: str, history: list = None) -> tuple:
    state = get_user_state(user_id)
    if history is None:
        history = state.get("history", [])
    
    context = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-5:]])
    logger.info(f"🔍 process_voice_message: user_id={user_id}")
    logger.info(f"🔍 user_text: {user_text}")
    logger.info(f"🔍 context: {context}")
    
    if not await is_safe_message(user_text):
        logger.info("⛔ Сообщение небезопасное (по списку слов)")
        return ("Извините, я не могу обсуждать эту тему. Давайте поговорим о чём-то другом.", "", False)

    has_cyrillic = bool(re.search(r'[а-яА-Я]', user_text))
    has_latin = bool(re.search(r'[a-zA-Z]', user_text))

    russian_requested = any(marker in user_text.lower() for marker in RUSSIAN_REQUEST)
    
    word_count = len(user_text.split())
    max_sentences = "1-3" if word_count <= 30 else "3-4"
    
    base_prompt = (
        "In your voice reply, ONLY continue the conversation naturally, ask a question, and do not mention corrections or translations. "
        "Do not correct mistakes, do not rephrase Russian. Just respond like a native speaker and keep the conversation going. "
        f"Keep your reply short ({max_sentences} sentences) and always end with a question.\n"
        "IMPORTANT: If the student discusses sexual, violent, drug-related, or other inappropriate topics, politely change the subject to something neutral (like weather, hobbies, daily routine) without explicitly saying you can't discuss it."
    )
    
    if russian_requested:
        system_prompt_reply = "You are a friendly English tutor. Respond in Russian, because the student asked for it. " + base_prompt
    else:
        system_prompt_reply = "You are a friendly English tutor. Always respond in English. " + base_prompt
    
    user_prompt_reply = (
        f"Context:\n{context}\n\n"
        f"Student: {user_text}\n"
        f"Your voice reply (natural, short, end with a question):"
    )
    
    logger.info("🔄 Вызов DeepSeek для генерации ответа")
    reply_text = chat(user_prompt_reply, system_message=system_prompt_reply, max_tokens=150, temperature=0.7)
    logger.info(f"🔍 reply_text (сырой от DeepSeek): '{reply_text}'")
    
    reply_text = reply_text.strip()
    if not reply_text:
        logger.warning("⚠️ DeepSeek вернул пустой ответ!")
        reply_text = "Sorry, I didn't get that. Could you repeat?"  # fallback
    
    if not reply_text.endswith('?'):
        reply_text += " What do you think?"
        logger.info(f"🔍 Добавлен вопрос: reply_text стал '{reply_text}'")
    
    correction_text = ""
    is_perfect = False
    
    if has_cyrillic:
        logger.info("🔄 Сообщение на русском, запрос перевода")
        translation_prompt = (
            f"The student said in Russian: {user_text}\n"
            f"Provide only the correct English translation, without any extra words. "
            f"Do not include the original Russian."
        )
        translation = chat(translation_prompt, system_message="You are a translator.", max_tokens=600, temperature=0.3)
        logger.info(f"🔍 translation: '{translation}'")
        correction_text = f"✔️ {translation}"
        
        if "russian_translation_count" not in state:
            state["russian_translation_count"] = 0
        state["russian_translation_count"] += 1
        if state["russian_translation_count"] % 3 == 0:
            correction_text += "\n\n💡 Try to say that in English next time – it's much better for practice!"
        set_user_state(user_id, state)
        
    else:
        logger.info("🔄 Сообщение на английском, проверка грамматики")
        check_prompt = (
            f"The student wrote: {user_text}\n"
            f"Check ONLY for grammar errors (verb forms, tenses, word order, articles, prepositions). "
            f"IGNORE punctuation and capitalization.\n"
            f"If there are errors, provide exactly in this format:\n"
            f"Line 1: corrected version as a single sentence without numbers or bullets\n"
            f"Line 2: <blockquote>explanation in Russian (пояснение на русском языке)</blockquote>\n"
            f"The explanation MUST be in Russian, not in English. Do not add any extra words before the <blockquote>.\n"
            f"If there are NO grammar errors, reply ONLY with the word 'NO_ERRORS' and NOTHING ELSE. Do not add explanations."
        )
        check_result = chat(check_prompt, system_message="You are a strict English teacher.", max_tokens=300, temperature=0.2)
        logger.info(f"🔍 check_result: '{check_result}'")
        
        if not check_result.strip():
            correction_text = "⚠️ Не удалось проверить грамматику. Попробуйте ещё раз."
            is_perfect = False
        elif check_result.strip() == "NO_ERRORS":
            is_perfect = True
            correction_text = ""
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
            
            if explanation:
                inner = re.sub(r'</?blockquote>', '', explanation)
                formatted_inner = format_explanation(inner)
                explanation = f"<blockquote>{formatted_inner}</blockquote>"
            
            correction_text = f"✔️ {corrected}\n{explanation}"
    
    logger.info(f"✅ Итоговый reply_text: '{reply_text}'")
    return reply_text, correction_text, is_perfect

async def process_roleplay_message(user_id: int, user_text: str, history: list = None) -> str:
    # ... (без изменений)