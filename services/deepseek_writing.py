import os
import logging
import re
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
    prompt = (
        "Ты – опытный преподаватель английского языка. Проверь письменный ответ на задание. "
        "Обращайся к пользователю напрямую на 'ты'. Не используй слова 'студент', 'ученик', 'автор' и т.п. "
        "Не используй Markdown-разметку (звёздочки, подчёркивания, решётки). Отвечай обычным текстом. "
        "Начинай ответ сразу с разбора ошибок, без вступлений. "
        "Дай 2-3 основные грамматические/лексические ошибки с исправлениями. "
        "Затем дай не более 3 советов по улучшению текста. "
        "В конце поставь оценку от 1 до 5 в формате: Оценка: X/5.\n\n"
        f"Задание: {task_text}\n"
        f"Уровень: {level} (beginner – начальный, intermediate – средний, expert – продвинутый).\n"
        f"Ключевые слова (по желанию): {', '.join(keywords)}\n"
        f"Ответ пользователя:\n{user_answer}\n"
    )

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.5
        )
        feedback = response.choices[0].message.content

        # Извлекаем оценку из конца текста
        score = 3  # по умолчанию
        match = re.search(r'Оценка:\s*(\d+)\s*[/]?\s*5', feedback)
        if match:
            score = int(match.group(1))
            if score < 1:
                score = 1
            elif score > 5:
                score = 5
            # Удаляем строку с оценкой из фидбека, чтобы не дублировать
            feedback = re.sub(r'Оценка:\s*\d+\s*[/]?\s*5', '', feedback).strip()

        return feedback, score

    except Exception as e:
        logger.error(f"DeepSeek API error in check_writing: {e}")
        raise