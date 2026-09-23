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

REQUEST_TIMEOUT = 90
MAX_RETRIES = 5
RETRY_DELAYS = [2, 4, 8, 16]


async def check_govorenie(task, task_type, user_text, level, duration) -> tuple:
    prompt = _get_govorenie_prompt(task_type, task, user_text, level, duration)

    # === БИНАРНЫЙ МАРКЕР В САМОМ НАЧАЛЕ ПРОМПТА ===
    prompt += (
        "\n\n!!! САМОЕ ПЕРВОЕ, ЧТО ТЫ ДЕЛАЕШЬ !!!\n"
        "Первой строкой своего ответа напиши РОВНО одно слово без разметки и знаков препинания:\n"
        "  OFF_TOPIC  — если ответ СОВЕРШЕННО НЕ ПО ТЕМЕ (нет ни одного слова, идеи, примера, факта по теме задания)\n"
        "  ON_TOPIC   — во всех остальных случаях (ответ по теме или ЧАСТИЧНО по теме)\n"
        "При ЛЮБОМ сомнении выбирай ON_TOPIC.\n"
        "Со второй строки — сам фидбек.\n"
    )

    # === ОБЩИЕ ПРАВИЛА ФОРМАТА ===
    prompt += (
        "\nВАЖНО: обращайся к пользователю на 'ты'.\n"
        "Используй HTML-разметку.\n"
        "ФОРМАТ ОТВЕТА:\n"
        "- Каждый критерий оформляй так: <b>Название критерия:</b> текст\n"
        "- После каждого критерия — ПУСТАЯ СТРОКА.\n"
        "- Последним блоком идёт <b>Советы:</b> — затем ОДИН <blockquote>...</blockquote>, "
        "внутри которого все советы пронумерованы (1., 2., 3.), каждый с новой строки. "
        "НЕ оформляй каждый совет отдельным <blockquote>. Все советы — внутри ОДНОГО <blockquote>.\n"
        "После закрывающего </blockquote> НЕ ставь точку, запятую или другой знак — сразу переходи к строке 'Оценка: X/5'.\n"
        "Максимум 3 совета.\n"
        "Похвала и смайлик — ТОЛЬКО если ответ ПО ТЕМЕ! Если не по теме — НИКАКОЙ похвалы и НИКАКОГО смайлика.\n"
        "Ни в коем случае не упоминай точки, запятые, паузы, интонацию, произношение.\n"
        "НИ СЛОВА ПРО ПУНКТУАЦИЮ.\n"
        "Игнорируй русские слова.\n"
        "В конце: Оценка: X/5."
    )

    # === ПРАВИЛО OFF-TOPIC В КОНЦЕ ===
    prompt += (
        "\n\n=== ОСОБОЕ ПРАВИЛО: ЕСЛИ OFF_TOPIC ===\n"
        "Если ты написал OFF_TOPIC первой строкой, то со второй строки напиши РОВНО ЭТО и НИЧЕГО БОЛЬШЕ:\n"
        "\n<b>Ваш ответ совершенно не соответствует теме.</b>\n"
        "\n<b>Советы:</b>\n"
        "<blockquote>1. Краткий совет, как начать отвечать по теме задания.\n"
        "2. Второй краткий совет по теме задания.\n"
        "3. Третий краткий совет по теме задания.</blockquote>\n"
        "\nВ конце: Оценка: 1/5.\n"
        "\nСТРОГО ЗАПРЕЩЕНО при OFF_TOPIC (не пиши НИЧЕГО из этого):\n"
        "- Любые критерии: 'Соответствие теме:', 'Словарный запас:', 'Грамматика:', 'Структура:', "
        "'Содержание ответа:', 'Полнота ответов:', 'Аргументация:', 'Точность:', 'Темп:'.\n"
        "- Разбор грамматических ошибок и примеры их исправления.\n"
        "- Анализ лексики, структуры, аргументации.\n"
        "- Цитирование фраз пользователя.\n"
        "- Похвалу, смайлики.\n"
        "=== КОНЕЦ ПРАВИЛА ===\n"
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

            feedback = re.sub(r'#{1,6}', '', feedback)
            feedback = re.sub(r'`', '', feedback)

            score = 3
            match = re.search(r'Оценка:\s*(\d+)\s*[/]?\s*5', feedback)
            if match:
                score = int(match.group(1))
                if score < 1:
                    score = 1
                elif score > 5:
                    score = 5
                feedback = re.sub(r'Оценка:\s*\d+\s*[/]?\s*5', '', feedback).strip()

            # Убираем висячие точки/запятые/двоеточия в конце
            feedback = re.sub(r'[\s\.\,\;\:]+$', '', feedback).strip()

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
            "- <b>Структура</b>: есть ли вступление, основная часть с аргументами/примерами и заключение. Оценивай этот критерий МЯГКО.\n"
            "- <b>Словарный запас</b>: разнообразие лексики, использование синонимов, сложных конструкций.\n"
            "- <b>Грамматика</b>: правильность построения предложений, времён, согласований.\n"
            "- <b>Советы</b>: дай 2–3 совета по улучшению. Советы пронумеруй (1., 2., 3.) и помести ВСЕ советы внутрь ОДНОГО <blockquote>...</blockquote>, каждый с новой строки.\n"
            "НЕ УПОМИНАЙ ТЕМП, ПАУЗЫ, ИНТОНАЦИЮ, ПРОИЗНОШЕНИЕ.\n"
            "Не упоминай пунктуацию.\n"
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
            "- <b>Полнота ответов</b>: даны ли ответы на все вопросы, указанные в задании.\n"
            "- <b>Грамматика</b>: есть ли грамматические ошибки.\n"
            "- <b>Словарный запас</b>: оцени разнообразие лексики.\n"
        )
        if requires_examples:
            base += (
                "- <b>Аргументация</b>: есть ли примеры, объяснения, логические связи.\n"
            )
        base += (
            "- <b>Советы</b>: дай 2–3 совета по улучшению. Советы пронумеруй (1., 2., 3.) и помести ВСЕ советы внутрь ОДНОГО <blockquote>...</blockquote>, каждый с новой строки.\n"
            "Не упоминай темп, скорость, паузы, интонацию, произношение — это не оценивается в интервью.\n"
            "Не упоминай пунктуацию, знаки препинания.\n"
            "Отвечай кратко, используй HTML-разметку."
        )
        return base
    else:
        return "Неизвестный тип задания."