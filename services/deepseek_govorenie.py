import os
import logging
import re
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Переменная окружения для ключа (можно использовать DeepSeek или OpenAI)
API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
if not API_KEY:
    logger.error("No API key found. Set DEEPSEEK_API_KEY or OPENAI_API_KEY")
    raise ValueError("API key is required")

# Для DeepSeek используйте base_url, для OpenAI – не указывайте (или укажите по умолчанию)
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")  # или None для OpenAI

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=BASE_URL if BASE_URL else None
)

async def check_govorenie(task, task_type, user_text, level, duration) -> tuple:
    """
    Отправляет запрос в ИИ для проверки устного ответа.
    Возвращает: (фидбек_текст, оценка_от_1_до_5)
    """
    prompt = _get_govorenie_prompt(task_type, task, user_text, level, duration)

    # Добавляем в промпт требование оценки в конце
    prompt += "\n\nВ конце поставь оценку от 1 до 5 в формате: Оценка: X/5. Отвечай обычным текстом, без звёздочек."

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat" if "deepseek" in BASE_URL else "gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        feedback = response.choices[0].message.content

        # Удаляем возможные Markdown-символы
        feedback = re.sub(r'\*\*?', '', feedback)
        feedback = re.sub(r'__?', '', feedback)
        feedback = re.sub(r'#{1,6}', '', feedback)
        feedback = re.sub(r'`', '', feedback)

        # Парсим оценку
        score = 3  # по умолчанию
        match = re.search(r'Оценка:\s*(\d+)\s*[/]?\s*5', feedback)
        if match:
            score = int(match.group(1))
            if score < 1:
                score = 1
            elif score > 5:
                score = 5
            feedback = re.sub(r'Оценка:\s*\d+\s*[/]?\s*5', '', feedback).strip()

        return feedback, score

    except Exception as e:
        logger.error(f"Ошибка при обращении к ИИ в check_govorenie: {e}")
        raise


def _get_govorenie_prompt(task_type: str, task: dict, user_text: str, level: str, duration: int) -> str:
    if task_type == "reading":
        return (
            f"Ты эксперт по английскому произношению. Пользователь (уровень {level}) прочитал текст:\n"
            f"'{task['text']}'\n"
            f"Распознанный текст:\n'{user_text}'\n"
            "Оцени по шкале 1-5 следующие критерии: чёткость (узнаваемость слов), ритм (паузы), общее впечатление. "
            "Дай краткий фидбек (3-4 предложения) с конкретными советами по улучшению произношения. "
            "Не пиши общие фразы, только конкретику."
        )

    elif task_type == "fluency":
        return (
            f"Ты эксперт по беглости речи. Пользователь (уровень {level}) говорил на тему '{task['topic']}' "
            f"в течение {duration} секунд.\n"
            f"Распознанный текст:\n'{user_text}'\n"
            "Оцени: 1) лексическое разнообразие (количество уникальных слов), "
            "2) наличие связок (however, moreover, in addition), "
            "3) общую беглость (запинки, повторы, паузы). "
            "Дай рекомендацию, как улучшить беглость (2-3 предложения)."
        )

    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        return (
            f"Ты экзаменатор. Пользователь (уровень {level}) отвечал на вопросы:\n{questions}\n"
            f"Его ответ (распознанный):\n'{user_text}'\n"
            "Определи, на все ли вопросы даны ответы. Оцени полноту ответов и грамматическую правильность. "
            "Дай рекомендации, как улучшить ответы (кратко, 2-3 предложения)."
        )

    else:
        return "Неизвестный тип задания."