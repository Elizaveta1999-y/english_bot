import os
import logging
import re
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
if not API_KEY:
    logger.error("No API key found. Set DEEPSEEK_API_KEY or OPENAI_API_KEY")
    raise ValueError("API key is required")

BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# ---------- НАСТРОЙКИ СЕТИ ----------
REQUEST_TIMEOUT = 90            # секунд на один запрос
MAX_RETRIES = 5                 # всего попыток
RETRY_DELAYS = [2, 4, 8, 16]    # паузы между попытками (сек)


async def check_govorenie(task, task_type, user_text, level, duration) -> tuple:
    """
    Проверяет ответ говорения через DeepSeek.
    При успехе: (feedback, score).
    При провале: (None, None) — вызывающий код сам показывает сообщение пользователю.
    """
    prompt = _get_govorenie_prompt(task_type, task, user_text, level, duration)

    # Глобальные правила (общие для всех типов)
    prompt += (
        "\n\nВАЖНО: обращайся к пользователю на 'ты'.\n"
        "Используй HTML-разметку.\n"
        "ФОРМАТ ОТВЕТА:\n"
        "- Каждый критерий оформляй так: <b>Название критерия:</b> текст\n"
        "- После каждого критерия — ПУСТАЯ СТРОКА.\n"
        "- Последним блоком идёт <b>Советы:</b> — затем ОДИН <blockquote>...</blockquote>, внутри которого все советы пронумерованы (1., 2., 3.), каждый с новой строки. "
        "НЕ оформляй каждый совет отдельным <blockquote>. Все советы — внутри ОДНОГО <blockquote>.\n"
        "Максимум 3 совета.\n"
        "Похвала и смайлик — ТОЛЬКО если ответ ПО ТЕМЕ! Если не по теме — НИКАКОЙ похвалы и НИКАКОГО смайлика.\n"
        "ЕСЛИ ОТВЕТ СОВЕРШЕННО НЕ ПО ТЕМЕ — НЕ ПИШИ ПОЛНЫЙ ФИДБЕК!\n"
        "Вместо этого напиши ТОЛЬКО:\n"
        "  <b>Ваш ответ совершенно не соответствует теме.</b>\n"
        "  Пожалуйста, будьте внимательны и прочитайте задание еще раз.\n"
        "  <b>Советы:</b>\n"
        "  <blockquote>1. Краткий совет, как можно начать.\n"
        "  2. Ещё один краткий совет.</blockquote>\n"
        "  И поставь оценку 1.\n"
        "НЕ ПИШИ ПРО СЛОВАРНЫЙ ЗАПАС, ГРАММАТИКУ, ТЕМП — ТОЛЬКО ЭТО.\n"
        "НЕ СТАВЬ СМАЙЛИК, НЕ ПИШИ ПОХВАЛУ.\n"
        "Ни в коем случае не упоминай точки, запятые, паузы, интонацию, произношение.\n"
        "НИ СЛОВА ПРО ПУНКТУАЦИЮ.\n"
        "Игнорируй русские слова.\n"
        "В конце: Оценка: X/5."
    )

    model = "deepseek-chat" if "deepseek" in BASE_URL else "gpt-3.5-turbo"
    url = f"{BASE_URL}/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.3
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise Exception(f"HTTP {resp.status}: {text[:200]}")

                    data = await resp.json()
                    feedback = data["choices"][0]["message"]["content"]

            if not feedback or not feedback.strip():
                raise Exception("Пустой ответ от DeepSeek")

            # Чистим Markdown
            feedback = re.sub(r'#{1,6}', '', feedback)
            feedback = re.sub(r'`', '', feedback)

            # Извлекаем оценку
            score = 3
            match = re.search(r'Оценка:\s*(\d+)\s*[/]?\s*5', feedback)
            if match:
                score = int(match.group(1))
                if score < 1:
                    score = 1
                elif score > 5:
                    score = 5
                feedback = re.sub(r'Оценка:\s*\d+\s*[/]?\s*5', '', feedback).strip()

            return feedback, score

        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(f"Govorenie: таймаут DeepSeek (попытка {attempt}/{MAX_RETRIES})")
        except aiohttp.ClientError as e:
            last_error = f"client_error: {e}"
            logger.warning(f"Govorenie: ClientError (попытка {attempt}/{MAX_RETRIES}): {e}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Govorenie: ошибка (попытка {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            await asyncio.sleep(delay)

    logger.error(f"Govorenie: все попытки исчерпаны. Последняя ошибка: {last_error}")
    return None, None


def _get_govorenie_prompt(task_type: str, task: dict, user_text: str, level: str, duration: int) -> str:
    level_instruction = {
        "beginner": "Оценивай мягко, прощай мелкие ошибки, акцент на базовом понимании.",
        "intermediate": "Оценивай средне, обращай внимание на грамматику и лексику, но не будь слишком строгим.",
        "advanced": "Оценивай объективно, без завышенных требований, но с учётом уровня."
    }.get(level, "Оценивай объективно.")

    word_count = len(user_text.split())

    if task_type == "reading":
        original_text = task.get('text', '')
        original_words = len(original_text.split())
        speed = round(original_words / (duration / 60), 1) if duration > 0 else 0

        speed_ranges = {
            "beginner": "80–120",
            "intermediate": "120–150",
            "advanced": "150–180"
        }
        speed_range = speed_ranges.get(level, "120–160")

        return (
            f"Ты – эксперт по чтению вслух. Проверь, насколько точно ты прочитал текст.\n"
            f"Оригинальный текст:\n{original_text}\n"
            f"Твой распознанный текст (игнорирую русские слова):\n{user_text}\n"
            f"Уровень: {level}.\n"
            f"Инструкция по строгости: {level_instruction}\n"
            f"Оригинальный текст содержит {original_words} слов. Ты читал {duration} секунд.\n"
            f"Твой темп чтения: {speed} слов в минуту.\n"
            f"Рекомендуемый темп для твоего уровня: {speed_range} слов в минуту.\n"
            "Оцени следующие критерии (и только их!):\n"
            "- <b>Точность</b>: все ли слова прочитаны правильно, есть ли пропуски или искажения. Укажи конкретные примеры.\n"
            "- <b>Темп</b>: соответствует ли твоя скорость рекомендуемому диапазону.\n"
            "- <b>Советы</b>: дай 1–2 совета по улучшению. Советы пронумеруй (1., 2.) и помести ВСЕ советы внутрь ОДНОГО <blockquote>...</blockquote>, каждый с новой строки.\n"
            "НЕ УПОМИНАЙ ЗНАКИ ПРЕПИНАНИЯ, ПАУЗЫ, ИНТОНАЦИЮ, ПРОИЗНОШЕНИЕ.\n"
            "Если ответ не по теме — сразу переходи к короткому ответу с оценкой 1.\n"
            "Отвечай кратко, используй HTML-разметку."
        )
    elif task_type == "fluency":
        return (
            f"Ты – эксперт по беглости речи. Ты говорил на тему '{task['topic']}' в течение {duration} секунд.\n"
            f"Твой распознанный текст (игнорирую русские слова):\n{user_text}\n"
            f"Уровень: {level}.\n"
            f"Количество слов в ответе: {word_count}.\n"
            f"Инструкция по строгости: {level_instruction}\n"
            "Оцени следующие критерии (и только их!):\n"
            "- <b>Соответствие теме</b>: насколько ответ соответствует заданной теме.\n"
            "- <b>Словарный запас</b>: разнообразие лексики, использование синонимов, сложных конструкций. Если лексика хорошая — напиши, что именно понравилось (например, «использованы синонимы: enjoy, love, like»).\n"
            "- <b>Грамматика</b>: правильность построения предложений, времён, согласований. Если ошибок нет — напиши «Ошибок нет». Если есть — укажи конкретные ошибки и как их исправить.\n"
            "- <b>Советы</b>: дай 2–3 совета по улучшению. Советы пронумеруй (1., 2., 3.) и помести ВСЕ советы внутрь ОДНОГО <blockquote>...</blockquote>, каждый с новой строки.\n"
            "НЕ УПОМИНАЙ ТЕМП, ПАУЗЫ, ИНТОНАЦИЮ, ПРОИЗНОШЕНИЕ.\n"
            "Не упоминай пунктуацию.\n"
            "Если ответ не по теме — сразу переходи к короткому ответу с оценкой 1.\n"
            "Отвечай кратко, используй HTML-разметку."
        )
    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        instruction = task.get('instruction', '')
        requires_examples = 'пример' in instruction.lower() or 'объясн' in instruction.lower() or 'example' in instruction.lower()

        base = (
            f"Ты – экзаменатор. Ты отвечал на вопросы:\n{questions}\n"
            f"Твои распознанные ответы (игнорирую русские слова):\n{user_text}\n"
            f"Уровень: {level}.\n"
            f"Инструкция по строгости: {level_instruction}\n"
            "Оцени ответ по следующим критериям (и только по ним!):\n"
            "- <b>Содержание ответа</b>: выполнены ли условия задания (вступление, заключение, слова-связки, зачитование вопроса, развёрнутость).\n"
            "- <b>Полнота ответов</b>: даны ли ответы на все вопросы, указанные в задании. Если пользователь просто перечитал вопрос, но не дал ответа — засчитывай как неполный ответ, и снижай балл.\n"
            "- <b>Грамматика</b>: есть ли грамматические ошибки. Если ошибок нет — напиши «Ошибок нет». Если есть — укажи конкретные ошибки и как их исправить.\n"
            "- <b>Словарный запас</b>: оцени разнообразие лексики. Если лексика хорошая — напиши что именно понравилось (например: «Хорошее разнообразие лексики, использованы синонимы (enjoy, love, like), сложные конструкции (I believe that, in my opinion)»). Если лексика бедная — укажи, что стоит добавить синонимов.\n"
        )
        if requires_examples:
            base += (
                "- <b>Аргументация</b>: есть ли примеры, объяснения, логические связи. Если примеров нет, укажи это и предложи добавить.\n"
            )
        base += (
            "- <b>Советы</b>: дай 2–3 совета по улучшению. Советы пронумеруй (1., 2., 3.) и помести ВСЕ советы внутрь ОДНОГО <blockquote>...</blockquote>, каждый с новой строки.\n"
            "Не упоминай темп, скорость, паузы, интонацию, произношение — это не оценивается в интервью.\n"
            "Не упоминай пунктуацию, знаки препинания.\n"
            "Если ответ не по теме — сразу переходи к короткому ответу с оценкой 1.\n"
            "Отвечай кратко, используй HTML-разметку."
        )
        return base
    else:
        return "Неизвестный тип задания."