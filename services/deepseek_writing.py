import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# Получаем API-ключ из переменных окружения
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    logger.error("DEEPSEEK_API_KEY not set in environment variables")
    raise ValueError("DEEPSEEK_API_KEY is required. Please set it in your environment.")

# Инициализируем клиент DeepSeek
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

def check_writing(task_text: str, user_answer: str, level: str, keywords: list) -> str:
    """
    Отправляет запрос к DeepSeek для проверки письменного ответа.

    Аргументы:
        task_text (str): Текст задания.
        user_answer (str): Ответ пользователя.
        level (str): Уровень (beginner, intermediate, advanced).
        keywords (list): Список ключевых слов, которые нужно было использовать.

    Возвращает:
        str: Фидбек от ИИ.
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
        "Оценка: ...\n"
        "Ошибки: ...\n"
        "Советы: ...\n"
        "Исправленный вариант: ..."
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek API error in check_writing: {e}")
        raise