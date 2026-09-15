import os
import logging
import re
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    logger.error("DEEPSEEK_API_KEY not set in environment variables")
    raise ValueError("DEEPSEEK_API_KEY is required. Please set it in your environment.")

BASE_URL = "https://api.deepseek.com/v1"

# ---------- НАСТРОЙКИ СЕТИ ----------
REQUEST_TIMEOUT = 90
MAX_RETRIES = 5
RETRY_DELAYS = [2, 4, 8, 16]


async def check_writing(task_text: str, user_answer: str, level: str, keywords: list, task_type: str) -> tuple:
    """
    Проверяет письменный ответ через DeepSeek.
    При успехе: (feedback, score).
    При провале: (None, None) — вызывающий код сам показывает сообщение пользователю.
    """
    # --- Формируем промпт ---
    if task_type == "email":
        criteria = (
            "Оценивай по следующим критериям:\n"
            "1. Структура письма (приветствие, основная часть, прощание).\n"
            "2. Грамматика и времена.\n"
            "3. Лексика (использование ключевых слов, уместность).\n"
            "4. Объём (соответствие заданию)."
        )
    elif task_type == "essay":
        criteria = (
            "Оценивай по следующим критериям:\n"
            "1. Соответствие теме и аргументированность (есть ли примеры, объяснения).\n"
            "2. Обязательная структура: начало (вступление), основная часть (аргументы/примеры), конец (заключение).\n"
            "3. Грамматика и лексика (связки, разнообразие слов).\n"
            "4. Логика и убедительность."
        )
    elif task_type == "post":
        criteria = (
            "Оценивай по следующим критериям:\n"
            "1. Использование хэштегов и смайликов (уместно, не перебор).\n"
            "2. Соответствие формату поста (краткость, выразительность).\n"
            "3. Грамматика и лексика.\n"
            "4. Оригинальность и вовлекающий стиль."
        )
    elif task_type == "story":
        criteria = (
            "Оценивай по следующим критериям:\n"
            "1. Начинается ли с 'One day' или аналогичного вступления.\n"
            "2. Использованы ли ключевые слова из задания.\n"
            "3. Связность и логика повествования.\n"
            "4. Грамматика и лексика (разнообразие)."
        )
    else:
        criteria = "Оценивай общие критерии: грамматика, лексика, соответствие теме."

    if level == "beginner":
        strictness = "мягкий. Хвали за попытку, даже если есть ошибки. Не требуй сложных конструкций."
    elif level == "intermediate":
        strictness = "средний. Обращай внимание на структуру, время, артикли, но не будь слишком строг."
    else:
        strictness = "строгий. Разбирай все ошибки: грамматику, лексику, стиль. Требуй высокого уровня."

    prompt = (
        f"Ты – опытный преподаватель английского языка. Проверь письменный ответ на задание.\n"
        f"Тип задания: {task_type}. Уровень пользователя: {level}.\n"
        f"Твой стиль проверки: {strictness}\n\n"
        f"Задание: {task_text}\n"
        f"Ключевые слова (можно использовать): {', '.join(keywords)}\n\n"
        f"Ответ пользователя:\n{user_answer}\n\n"
        f"{criteria}\n\n"
        "Оцени ответ по плану. Отвечай на русском языке, обращайся к пользователю на 'ты'.\n"
        "ПЕРВЫМ пунктом укажи <b>Соответствие теме:</b> – процент (0-100) и краткий комментарий.\n"
        "Если соответствие НИЗКОЕ (менее 30%), то НЕ РАЗБИРАЙ ОШИБКИ. Вместо этого напиши короткое сообщение:\n"
        "<b>Соответствие теме:</b> Низкое (0-30%). Текст не связан с заданием. Попробуй начать с … (дай 2-3 примера начала).\n"
        "И сразу переходи к <b>Советы по улучшению:</b> (коротко) и <b>Оценка: 1/5</b>.\n\n"
        "Если соответствие ВЫСОКОЕ (более 30%), то дай полный разбор:\n"
        "<b>Грамматика:</b> – перечисли 2-3 основные ошибки с исправлениями.\n"
        "<b>Лексика:</b> – укажи неточности, повторы, неудачные выражения.\n"
        "<b>Советы по улучшению:</b> – дай 2-3 практических совета, как сделать текст лучше. "
        "ВАЖНО: все советы должны быть в ОДНОМ теге <blockquote>...</blockquote>, внутри которого советы разделены цифрами 1., 2., 3. "
        "НЕ разделяй советы на отдельные <blockquote> и НЕ оборачивай в цитату ничего другого (критерии, оценку, похвалу).\n"
        "Пример оформления советов:\n"
        "<b>Советы по улучшению:</b>\n"
        "<blockquote>1. Используй более разнообразную лексику. 2. Обрати внимание на порядок слов. 3. Добавь пример.</blockquote>\n"
        "Если текст действительно хорош (оценка 4 или 5), добавь ОДНУ короткую похвалу и РОВНО ОДИН смайлик из набора: 👍🏻, 👏🏻, 🤩, 😉. "
        "Во всём ответе должен быть только один смайлик. Если текст не очень хорош, смайлик не добавляй.\n"
        "В конце поставь <b>Оценка: X/5</b> (именно в таком формате).\n"
        "Форматируй ответ с помощью HTML: критерии жирным (<b>), советы внутри <blockquote>.\n"
        "Не используй Markdown-разметку (звёздочки, `>` и т.п.).\n"
        "Ответ должен быть кратким, не более 5-6 предложений в сумме (кроме советов).\n"
        "Начинай ответ сразу с разбора, без приветствий и вступлений.\n"
        "Не пиши 'Привет', 'Здравствуйте' и т.п.\n"
        "Не используй другие эмодзи, кроме разрешённого одного.\n"
    )

    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0.5
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

            # Извлекаем оценку
            score = 3
            match = re.search(r'<b>Оценка:\s*(\d+)\s*/\s*5</b>', feedback)
            if not match:
                match = re.search(r'Оценка:\s*(\d+)\s*/\s*5', feedback)
            if match:
                score = int(match.group(1))
                if score < 1:
                    score = 1
                elif score > 5:
                    score = 5
                feedback = re.sub(r'<b>Оценка:\s*\d+\s*/\s*5</b>', '', feedback).strip()
                feedback = re.sub(r'Оценка:\s*\d+\s*/\s*5', '', feedback).strip()

            return feedback, score

        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(f"Writing: таймаут DeepSeek (попытка {attempt}/{MAX_RETRIES})")
        except aiohttp.ClientError as e:
            last_error = f"client_error: {e}"
            logger.warning(f"Writing: ClientError (попытка {attempt}/{MAX_RETRIES}): {e}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Writing: ошибка (попытка {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            await asyncio.sleep(delay)

    logger.error(f"Writing: все попытки исчерпаны. Последняя ошибка: {last_error}")
    return None, None