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

REQUEST_TIMEOUT = 120
MAX_ATTEMPTS = 5
RETRY_DELAYS = [2, 4, 8, 16]

MODEL_CHEAP = "deepseek-v4-flash"
MODEL_SMART = "deepseek-v4-pro"


class DeepSeekTutorError(Exception):
    """Ошибка при обращении к DeepSeek API (Наставник)."""
    pass


async def _request(
    prompt: str,
    system_message: str = None,
    max_tokens: int = 1500,
    temperature: float = 0.4,
    model: str = MODEL_SMART,
) -> str:
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        # Отключаем reasoning для ВСЕХ моделей Наставника,
        # чтобы не было пустых ответов.
        "thinking": {"type": "disabled"},
    }

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise DeepSeekTutorError(f"HTTP {resp.status}: {text[:200]}")

                    data = await resp.json()
                    choice = data["choices"][0]
                    content = choice["message"].get("content") or ""
                    reasoning = choice["message"].get("reasoning_content") or ""
                    finish_reason = choice.get("finish_reason")

                    if not content.strip():
                        snippet = (reasoning[:100] + "...") if reasoning else "нет"
                        logger.warning(
                            f"Tutor: пустой content (модель {model}). "
                            f"reasoning=[{snippet}] "
                            f"finish_reason={finish_reason}"
                        )
                        raise DeepSeekTutorError("Пустой ответ от DeepSeek")

                    return content

        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(f"Tutor timeout (попытка {attempt}/{MAX_ATTEMPTS}, модель {model})")
        except aiohttp.ClientError as e:
            last_error = f"client_error: {e}"
            logger.warning(f"Tutor ClientError (попытка {attempt}/{MAX_ATTEMPTS}): {e}")
        except DeepSeekTutorError as e:
            last_error = str(e)
            logger.warning(f"Tutor error (попытка {attempt}/{MAX_ATTEMPTS}): {e}")
        except Exception as e:
            last_error = f"unknown: {e}"
            logger.error(f"Tutor unknown error (попытка {attempt}/{MAX_ATTEMPTS}): {e}", exc_info=True)

        if attempt < MAX_ATTEMPTS:
            delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            await asyncio.sleep(delay)

    logger.error(f"Tutor: все попытки исчерпаны (модель {model}). Последняя ошибка: {last_error}")
    raise DeepSeekTutorError(f"Все попытки исчерпаны: {last_error}")


async def chat_smart(
    prompt: str,
    system_message: str = None,
    max_tokens: int = 1500,
    temperature: float = 0.4,
) -> str:
    """Умная модель — ТОЛЬКО для Наставника. Reasoning отключён."""
    return await _request(
        prompt,
        system_message=system_message,
        max_tokens=max_tokens,
        temperature=temperature,
        model=MODEL_SMART,
    )