import os
import uuid
import logging
import base64
import aiohttp

logger = logging.getLogger(__name__)

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"
REQUEST_TIMEOUT = 30


def _get_auth_header() -> str:
    credentials = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def create_payment(user_id: int, amount: float, description: str, return_url: str) -> dict:
    """
    Создаёт платёж в ЮKassa.
    Возвращает dict {"payment_id": ..., "confirmation_url": ..., "status": ...} или None.
    """
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("YooKassa: не заданы SHOP_ID или SECRET_KEY")
        return None

    idempotence_key = str(uuid.uuid4())

    headers = {
        "Authorization": _get_auth_header(),
        "Idempotence-Key": idempotence_key,
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "description": description,
        "metadata": {
            "user_id": user_id,
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(YOOKASSA_API_URL, headers=headers, json=payload) as resp:
                data = await resp.json()
                if resp.status not in (200, 201):
                    logger.error(f"YooKassa create_payment: {resp.status} — {data}")
                    return None
                return {
                    "payment_id": data.get("id"),
                    "confirmation_url": data.get("confirmation", {}).get("confirmation_url"),
                    "status": data.get("status"),
                }
    except Exception as e:
        logger.error(f"YooKassa create_payment error: {e}", exc_info=True)
        return None


async def get_payment_status(payment_id: str) -> dict:
    """Проверяет статус платежа в ЮKassa."""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("YooKassa: не заданы SHOP_ID или SECRET_KEY")
        return None

    url = f"{YOOKASSA_API_URL}/{payment_id}"
    headers = {"Authorization": _get_auth_header()}

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"YooKassa get_payment_status: {resp.status} — {data}")
                    return None
                return data
    except Exception as e:
        logger.error(f"YooKassa get_payment_status error: {e}", exc_info=True)
        return None