import json
import re
from services.deepseek import chat

async def generate_task(topic: str) -> dict:
    """Генерирует задание по теме через DeepSeek, возвращает словарь с task_text и answers"""
    prompt = f"""
Ты учитель английского. Придумай задание по теме "{topic}" для уровня A2-B1.
Задание должно проверять понимание разницы между Present Simple и Present Continuous.
Формат: 5 предложений с пропусками (choose the correct form). Для каждого предложения укажи правильный ответ.
Верни строго в формате JSON без лишних пояснений:
{{
    "task_text": "1. She usually (watch/watches) TV in the evening.\\n2. Look! He (runs/is running) to school.\\n3. They (play/are playing) football every Sunday.\\n4. I (think/am thinking) you are right.\\n5. We (have/are having) dinner now.",
    "answers": ["watches", "is running", "play", "think", "are having"]
}}
"""
    response = chat(prompt, max_tokens=800, temperature=0.7)
    # Пытаемся извлечь JSON из ответа
    try:
        # Ищем блок с JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            task_dict = json.loads(json_match.group())
            if "task_text" in task_dict and "answers" in task_dict:
                return task_dict
    except Exception as e:
        print(f"JSON parse error: {e}")
    # Fallback: возвращаем заглушку
    return {
        "task_text": "1. She usually (watch/watches) TV.\n2. Look! He (runs/is running).\n3. They (play/are playing) football every Sunday.\n4. I (think/am thinking) you are right.\n5. We (have/are having) dinner now.",
        "answers": ["watches", "is running", "play", "think", "are having"]
    }

async def check_answer(student_answer: str, task: dict) -> str:
    """Проверяет ответ студента, возвращает фидбек"""
    prompt = f"""
Ты преподаватель английского. Задание:
{task['task_text']}

Правильные ответы: {task['answers']}

Ответ студента: {student_answer}

Оцени ответ. Если все правильно – похвали и предложи следующее задание.
Если есть ошибки – укажи, какие именно, объясни правило (Present Simple vs Continuous) и предложи попробовать ещё раз или дай подсказку.
Ответ напиши на русском, дружелюбно, до 5 предложений.
"""
    return chat(prompt, max_tokens=500, temperature=0.5)