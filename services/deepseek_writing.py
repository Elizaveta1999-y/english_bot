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
    """
    Отправляет запрос к DeepSeek для проверки письменного ответа.
    Возвращает: (фидбек_текст, оценка_от_1_до_5)
    """
    prompt = (
        f"Ты – опытный преподаватель английского языка. Проверь письменный ответ на задание.\n"
        f"Задание: {task_text}\n"
        f"Уровень студента: {level} (beginner – начальный, intermediate – средний, expert – продвинутый).\n"
        f"Ключевые слова, которые нужно было использовать: {', '.join(keywords)}\n"
        f"Ответ пользователя:\n{user_answer}\n\n"
        "Дай развёрнутый фидбек на русском языке. Обращайся к пользователю напрямую на 'ты'. Не используй слова 'студент', 'ученик', 'автор' и т.п.\n"
        "Не используй Markdown, звёздочки, подчёркивания, решётки. Отвечай обычным текстом.\n"
        "Не начинай с вступлений типа 'Результат проверки' или 'Вот подробный фидбек'. Начинай сразу с разбора ошибок.\n"
        "Структура фидбека:\n"
        "- Сначала перечисли основные ошибки (грамматика, лексика, соответствие теме, структура). Будь конкретен, указывай исправления.\n"
        "- Затем дай не более 3 советов по улучшению.\n"
        "- В конце поставь оценку по шкале от 1 до 5 в формате: Оценка: X/5\n"
        "Никакой другой информации в конце не добавляй.\n"
        "Если ответ содержит темы насилия, секса, экстремизма или политики – не анализируй его. Верни только одну фразу: 'Извините, я не могу обрабатывать сообщения на такие темы. Пожалуйста, напишите что-то другое.' и поставь оценку 1/5."
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.5
        )
        feedback = response.choices[0].message.content

        # Извлечение оценки (ищем число от 1 до 5 после "Оценка:")
        score_match = re.search(r'Оценка:\s*(\d+)\s*[/]?\s*5', feedback)
        if score_match:
            score = int(score_match.group(1))
            if score < 1:
                score = 1
            elif score > 5:
                score = 5
        else:
            score = 3  # по умолчанию

        # Убираем из фидбека строку с оценкой, чтобы она была только в конце сообщения (но она уже в конце, если ИИ правильно следовал инструкции)
        # Если оценка всё же оказалась в середине, можно оставить как есть – но мы не будем её удалять, просто вернём весь фидбек.

        return feedback, score

    except Exception as e:
        logger.error(f"DeepSeek API error in check_writing: {e}")
        raise