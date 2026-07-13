import openai
import os

# Если используете DeepSeek, раскомментируйте и укажите ключ
# DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# openai.api_key = DEEPSEEK_API_KEY
# openai.base_url = "https://api.deepseek.com/v1"

async def check_govorenie(task, task_type, user_text, level, duration):
    """
    Отправляет запрос в DeepSeek/OpenAI для проверки устного ответа.
    """
    prompt = _get_govorenie_prompt(task_type, task, user_text, level, duration)

    # Здесь используйте вашу модель
    # Для DeepSeek:
    # response = openai.ChatCompletion.create(
    #     model="deepseek-chat",
    #     messages=[{"role": "user", "content": prompt}],
    #     max_tokens=300,
    #     temperature=0.3
    # )
    # Для OpenAI:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.3
    )
    return response.choices[0].message.content


def _get_govorenie_prompt(task_type: str, task: dict, user_text: str, level: str, duration: int) -> str:
    if task_type == "reading":
        return (
            f"Ты эксперт по английскому произношению. Пользователь (уровень {level}) прочитал текст:\n"
            f"'{task['text']}'\n"
            f"Распознанный текст:\n'{user_text}'\n"
            "Оцени по шкале 1-10 три критерия: чёткость (узнаваемость слов), ритм (паузы), общее впечатление. "
            "Дай короткий фидбек (3-4 предложения) с конкретными советами по улучшению произношения. "
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
            "Поставь общий балл (1-10) и дай рекомендацию, как улучшить беглость (2-3 предложения)."
        )

    elif task_type == "interview":
        questions = "\n".join([f"{i+1}. {q}" for i, q in enumerate(task['questions'])])
        return (
            f"Ты экзаменатор. Пользователь (уровень {level}) отвечал на вопросы:\n{questions}\n"
            f"Его ответ (распознанный):\n'{user_text}'\n"
            "Определи, на все ли вопросы даны ответы. Оцени полноту ответов (1-10) и грамматическую правильность. "
            "Дай рекомендации, как улучшить ответы (кратко, 2-3 предложения)."
        )

    else:
        return "Неизвестный тип задания."