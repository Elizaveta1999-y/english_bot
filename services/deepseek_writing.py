import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    logger.error("DEEPSEEK_API_KEY not set in environment variables")
    raise ValueError("DEEPSEEK_API_KEY is required. Please set it in your environment.")

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

async def check_writing(task_text: str, user_answer: str, level: str, keywords: list) -> tuple:
    """
    Отправляет запрос к DeepSeek для проверки письменного ответа.

    Возвращает: (фидбек_текст, оценка_от_1_до_5)
    """
    prompt = (
        f"Ты – опытный преподаватель английского языка. Проверь письменный ответ студента на задание.\n"
        f"Задание: {task_text}\n"
        f"Уровень студента: {level} (beginner – начальный, intermediate – средний, expert – продвинутый).\n"
        f"Ключевые слова, которые нужно было использовать: {', '.join(keywords)}\n"
        f"Ответ студента:\n{user_answer}\n\n"
        "Дай развёрнутый фидбек на русском языке. Оцени:\n"
        "1) Грамматика и лексика (укажи основные ошибки и дай правильные варианты).\n"
        "2) Соответствие теме и использование ключевых слов.\n"
        "3) Структура и связность текста.\n"
        "В конце дай исправленный вариант текста студента (исправь ошибки, но сохрани его стиль).\n"
        "Формат ответа:\n"
        "Оценка: ... (число от 1 до 5)\n"
        "Ошибки: ...\n"
        "Советы: ...\n"
        "Исправленный вариант: ..."
    )

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.5
        )
        feedback = response.choices[0].message.content

        # Попытка извлечь оценку из текста (если есть "Оценка: 4/5" или подобное)
        import re
        score_match = re.search(r'Оценка:\s*(\d+)\s*[/]?\s*5', feedback)
        if score_match:
            score = int(score_match.group(1))
            if score < 1:
                score = 1
            elif score > 5:
                score = 5
        else:
            # Если оценка не найдена, ставим по умолчанию 3
            score = 3

        return feedback, score

    except Exception as e:
        logger.error(f"DeepSeek API error in check_writing: {e}")
        # Пробрасываем исключение дальше, чтобы writing.py обработал
        raise