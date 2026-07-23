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
    prompt = _get_govorenie_prompt(task_type, task, user_text, level, duration)

    # ============================================================
    # 🔥 НОВАЯ ИНСТРУКЦИЯ – убираем звёздочки, оценки в середине
    # ============================================================
    prompt += (
        "\n\nВыдай фидбек в виде обычного текста, без звёздочек, подчёркиваний и других знаков форматирования. "
        "Не используй заголовки типа 'Для чтения вслух:' или 'Ошибки:'. Пиши просто перечислением. "
        "Обращайся к пользователю на 'ты'. Не используй слова 'студент', 'ученик', 'автор'. "
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

        # Удаляем возможные звёздочки и другие Markdown
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

# ============================================================
# 🔥 НОВЫЕ ПРОМПТЫ – отдельные для каждого типа, без оценок в середине
# ============================================================
def _get_govorenie_prompt(task_type: str, task: dict, user_text: str, level: str, duration: int) -> str:
    if task_type == "reading":
        return (
            f"Ты – эксперт по чтению вслух. Проверь, насколько точно пользователь прочитал текст.\n"
            f"Оригинальный текст:\n{task['text']}\n"
            f"Распознанный текст пользователя:\n{user_text}\n"
            f"Уровень пользователя: {level}.\n"
            "Твоя задача:\n"
            "- Сравни оригинал и распознанный текст. Найди пропущенные слова и слова, которые были искажены (укажи правильный вариант).\n"
            "- Дай 2–3 конкретных совета по улучшению чтения (например, обратить внимание на определённые слова, не проглатывать окончания и т.д.).\n"
            "Не упоминай лексическое разнообразие или структуру – это не относится к чтению.\n"
            "Отвечай кратко и по делу."
        )
    elif task_type == "fluency":
        return (
            f"Ты – эксперт по беглости речи. Пользователь говорил на тему '{task['topic']}' в течение {duration} секунд.\n"
            f"Распознанный текст:\n{user_text}\n"
            f"Уровень пользователя: {level}.\n"
            "Твоя задача:\n"
            "- Оцени лексическое разнообразие: сколько уникальных слов, есть ли синонимы, не повторяются ли одни и те же слова.\n"
            "- Оцени связность: есть ли вводные конструкции (however, moreover, in addition), логические связки.\n"
            "- Дай 2–3 конкретных совета, как улучшить беглость и лексику (например, добавить синонимы, использовать сложные предложения).\n"
            "Отвечай кратко и по делу."
        )
    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        return (
            f"Ты – экзаменатор. Пользователь отвечал на вопросы:\n{questions}\n"
            f"Его распознанные ответы:\n{user_text}\n"
            f"Уровень пользователя: {level}.\n"
            "Твоя задача:\n"
            "- Оцени полноту ответов: на все ли вопросы даны развёрнутые ответы.\n"
            "- Оцени грамматику и аргументацию: есть ли примеры, объяснения, логические связи.\n"
            "- Дай 2–3 конкретных совета, как улучшить ответы (например, раскрыть какой-то вопрос подробнее, добавить примеры).\n"
            "Отвечай кратко и по делу."
        )
    else:
        return "Неизвестный тип задания."