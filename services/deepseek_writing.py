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

async def check_writing(task_text: str, user_answer: str, level: str, keywords: list) -> tuple:
    prompt = (
        "Ты – опытный преподаватель английского языка. Проверь письменный ответ на задание. "
        "Обращайся к пользователю напрямую на 'ты'. Не используй слова 'студент', 'ученик', 'автор' и т.п. "
        "ОТВЕЧАЙ ТОЛЬКО ОБЫЧНЫМ ТЕКСТОМ, БЕЗ ЗВЁЗДОЧЕК, ПОДЧЁРКИВАНИЙ, РЕШЁТОК И ДРУГИХ СИМВОЛОВ ФОРМАТИРОВАНИЯ. "
        "Начинай ответ сразу с разбора ошибок, без приветствий, вступлений и обращений. Не пиши 'Привет', 'Здравствуйте' и т.п. "
        "Дай 2-3 основные грамматические/лексические ошибки с исправлениями. "
        "Затем дай не более 3 советов по улучшению текста. "
        "В конце поставь оценку от 1 до 5 в формате: Оценка: X/5.\n\n"
        f"Задание: {task_text}\n"
        f"Уровень: {level} (beginner – начальный, intermediate – средний, expert – продвинутый).\n"
        f"Ключевые слова (по желанию): {', '.join(keywords)}\n"
        f"Ответ пользователя:\n{user_answer}\n"
    )

    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.5
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                resp.raise_for_status()
                data = await resp.json()
                feedback = data["choices"][0]["message"]["content"]

        # Удаляем Markdown-символы
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

    except asyncio.TimeoutError:
        logger.error("Timeout while calling DeepSeek API in check_writing")
        return "Превышено время ожидания ответа. Попробуйте позже.", 3
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error in check_writing: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in check_writing: {e}")
        raise