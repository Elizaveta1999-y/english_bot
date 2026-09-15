import os
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    logger.error("DEEPSEEK_API_KEY not set in environment variables")
    raise ValueError("DEEPSEEK_API_KEY is required. Please set it in your environment.")

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Сколько ждём ответа от DeepSeek (секунд)
REQUEST_TIMEOUT = 90
# Сколько попыток всего (1 + 4 повтора)
MAX_ATTEMPTS = 5
# Паузы между попытками (экспоненциальные)
RETRY_DELAYS = [2, 4, 8, 16]


class DeepSeekError(Exception):
    """Ошибка при обращении к DeepSeek API. Лови её в режимах и показывай пользователю понятное сообщение."""
    pass


async def chat(
    prompt: str,
    system_message: str = None,
    max_tokens: int = 800,
    temperature: float = 0.7,
) -> str:
    """
    Асинхронный запрос к DeepSeek.
    Бросает DeepSeekError, если все попытки провалились.
    """
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise DeepSeekError(f"HTTP {resp.status}: {text[:200]}")

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]

                    if not content or not content.strip():
                        raise DeepSeekError("Пустой ответ от DeepSeek")

                    return content

        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(f"DeepSeek timeout (попытка {attempt}/{MAX_ATTEMPTS})")
        except aiohttp.ClientError as e:
            last_error = f"client_error: {e}"
            logger.warning(f"DeepSeek ClientError (попытка {attempt}/{MAX_ATTEMPTS}): {e}")
        except DeepSeekError as e:
            last_error = str(e)
            logger.warning(f"DeepSeek error (попытка {attempt}/{MAX_ATTEMPTS}): {e}")
        except Exception as e:
            last_error = f"unknown: {e}"
            logger.error(f"DeepSeek unknown error (попытка {attempt}/{MAX_ATTEMPTS}): {e}", exc_info=True)

        # Пауза перед следующей попыткой
        if attempt < MAX_ATTEMPTS:
            delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            await asyncio.sleep(delay)

    logger.error(f"DeepSeek: все попытки исчерпаны. Последняя ошибка: {last_error}")
    raise DeepSeekError(f"Все попытки исчерпаны: {last_error}")