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

async def check_writing(task_text: str, user_answer: str, level: str, keywords: list, task_type: str) -> tuple:
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
            "2. Структура (вступление, основная часть, заключение).\n"
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
    else:  # expert
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
        "ПЕРВЫМ пунктом укажи **Соответствие теме:** – процент (0-100) и краткий комментарий.\n"
        "Если соответствие НИЗКОЕ (менее 30%), то НЕ РАЗБИРАЙ ОШИБКИ. Вместо этого напиши короткое сообщение:\n"
        "**Соответствие теме:** Низкое (0-30%). Текст не связан с заданием. Попробуй начать с … (дай 2-3 примера начала).\n"
        "И сразу переходи к **Советы по улучшению:** (коротко) и **Оценка: 1/5**.\n\n"
        "Если соответствие ВЫСОКОЕ (более 30%), то дай полный разбор:\n"
        "**Грамматика:** – перечисли 2-3 основные ошибки с исправлениями.\n"
        "**Лексика:** – укажи неточности, повторы, неудачные выражения.\n"
        "**Советы по улучшению:** – дай 2-3 практических совета, как сделать текст лучше (оформи как цитату с '>').\n"
        "Максимум одна похвала, если текст действительно хорош.\n"
        "В конце поставь **Оценка: X/5**.\n"
        "Форматируй ответ с помощью Markdown: заголовки жирным (**).\n"
        "Не используй HTML-теги.\n"
        "Ответ должен быть кратким, не более 5-6 предложений в сумме (кроме советов).\n"
        "Начинай ответ сразу с разбора, без приветствий и вступлений.\n"
        "Не пиши 'Привет', 'Здравствуйте' и т.п.\n"
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

    # ---------- НАСТРОЙКИ РЕТРАЯ ----------
    MAX_RETRIES = 3
    RETRY_DELAY = 1.5  # секунд между попытками

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    feedback = data["choices"][0]["message"]["content"]

            # Проверяем, что ответ не пустой
            if feedback and feedback.strip():
                # Убираем лишние HTML-теги
                feedback = re.sub(r'<[^>]+>', '', feedback)

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
            else:
                # Пустой ответ – логируем и пробуем снова
                logger.warning(
                    f"Пустой ответ от DeepSeek (попытка {attempt}/{MAX_RETRIES}) "
                    f"для user_answer: {user_answer[:50]}..."
                )
                if attempt == MAX_RETRIES:
                    # Последняя попытка – возвращаем сообщение об ошибке
                    error_msg = (
                        "Не удалось получить оценку от ИИ. Попробуйте позже или обратитесь в поддержку.\n"
                        "Ваш ответ не был засчитан, вы можете отправить его снова."
                    )
                    return error_msg, 3
                await asyncio.sleep(RETRY_DELAY)
                continue

        except asyncio.TimeoutError:
            logger.error(f"Таймаут DeepSeek API (попытка {attempt}/{MAX_RETRIES})")
            if attempt == MAX_RETRIES:
                return "Превышено время ожидания ответа. Попробуйте позже.", 3
            await asyncio.sleep(RETRY_DELAY)
            continue

        except aiohttp.ClientError as e:
            logger.error(f"HTTP ошибка DeepSeek API (попытка {attempt}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES:
                return f"Ошибка связи с сервером. Попробуйте позже. ({e})", 3
            await asyncio.sleep(RETRY_DELAY)
            continue

        except Exception as e:
            logger.error(f"Неизвестная ошибка в check_writing (попытка {attempt}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES:
                return "Произошла непредвиденная ошибка. Попробуйте позже.", 3
            await asyncio.sleep(RETRY_DELAY)
            continue

    # Если цикл завершился без return (защита)
    return "Не удалось получить оценку. Попробуйте позже.", 3