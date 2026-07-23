import os
import logging
import re
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
if not API_KEY:
    logger.error("No API key found. Set DEEPSEEK_API_KEY or OPENAI_API_KEY")
    raise ValueError("API key is required")

BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

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

    # Добавляем общие инструкции
    prompt += (
        "\n\nВыдай фидбек строго по следующей структуре (без Markdown, без звёздочек):\n"
        "Для чтения вслух:\n"
        "- Сравнение с оригиналом: процент совпадения, список пропущенных слов, список слов с ошибками (если есть).\n"
        "- Конкретные советы (2–3 пункта).\n"
        "Для беглости:\n"
        "- Лексическое разнообразие (упомяни, каких слов не хватает).\n"
        "- Связность и структура (есть ли вводные конструкции, логика).\n"
        "- Конкретные советы (2–3 пункта).\n"
        "Для интервью:\n"
        "- Полнота ответов (на все ли вопросы даны ответы, достаточно ли развёрнуто).\n"
        "- Грамматика и аргументация (основные ошибки, примеры).\n"
        "- Конкретные советы (2–3 пункта).\n"
        "Не используй слова 'студент', 'ученик', 'автор'. Обращайся на 'ты'.\n"
        "В конце поставь общую оценку от 1 до 5 в формате: Оценка: X/5."
    )

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat" if "deepseek" in BASE_URL else "gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3
        )
        feedback = response.choices[0].message.content

        # Удаляем Markdown
        feedback = re.sub(r'\*\*?', '', feedback)
        feedback = re.sub(r'__?', '', feedback)
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

        return feedback, score

    except Exception as e:
        logger.error(f"Ошибка при обращении к ИИ в check_govorenie: {e}")
        raise

def _get_govorenie_prompt(task_type: str, task: dict, user_text: str, level: str, duration: int) -> str:
    if task_type == "reading":
        return (
            f"Ты – опытный преподаватель английского языка. Проверь, насколько точно пользователь прочитал текст вслух.\n"
            f"Оригинальный текст:\n{task['text']}\n"
            f"Распознанный текст пользователя:\n{user_text}\n"
            f"Уровень пользователя: {level}.\n"
            "Сравни оригинальный текст и распознанный. Найди слова, которые были пропущены или искажены. "
            "Дай конкретные замечания: перечисли пропущенные слова и слова, которые были изменены (укажи правильный вариант). "
            "Дай 2–3 совета по улучшению произношения и внимательности."
        )
    elif task_type == "fluency":
        return (
            f"Ты – эксперт по беглости речи. Пользователь говорил на тему '{task['topic']}' в течение {duration} секунд.\n"
            f"Распознанный текст:\n{user_text}\n"
            f"Уровень пользователя: {level}.\n"
            "Оцени лексическое разнообразие (сколько уникальных слов, есть ли синонимы). "
            "Оцени связность: использует ли пользователь вводные слова (however, moreover, in addition), логические связки. "
            "Дай 2–3 конкретных совета, как улучшить беглость и лексику."
        )
    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        return (
            f"Ты – экзаменатор. Пользователь отвечал на вопросы:\n{questions}\n"
            f"Его распознанные ответы:\n{user_text}\n"
            f"Уровень пользователя: {level}.\n"
            "Оцени полноту ответов (на все ли вопросы даны развёрнутые ответы). "
            "Оцени грамматику и аргументацию (есть ли примеры, объяснения). "
            "Дай 2–3 конкретных совета, как улучшить ответы."
        )
    else:
        return "Неизвестный тип задания."