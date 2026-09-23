import os
import io
import json
import logging
from decimal import Decimal
import httpx
from nalogo import Client

logger = logging.getLogger(__name__)

DEVICE_ID = "english-bot-admin"
NALOGO_INN = os.getenv("NALOGO_INN") or os.getenv("NALOG_INN")
NALOGO_PASSWORD = os.getenv("NALOGO_PASSWORD") or os.getenv("NALOG_PASSWORD")


def _extract_bearer_token(token_json: str) -> str | None:
    """Из сохранённого JSON достаёт поле token — для заголовка Authorization."""
    try:
        parsed = json.loads(token_json)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(parsed, dict):
        for key in ("token", "accessToken", "access_token", "jwt"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return None


async def _login_by_password() -> str | None:
    """Логинится по ИНН+паролю, сохраняет новый JSON в БД. Возвращает JSON-строку."""
    from admin_app import save_nalogo_token

    if not NALOGO_INN or not NALOGO_PASSWORD:
        logger.error("NaloGO: NALOGO_INN или NALOGO_PASSWORD не заданы")
        return None

    try:
        client = Client(device_id=DEVICE_ID)
        token_json = await client.create_new_access_token(NALOGO_INN, NALOGO_PASSWORD)

        if not token_json:
            logger.error("NaloGO: create_new_access_token вернул пусто")
            return None

        # Если вернулась dict — конвертируем в JSON-строку
        if isinstance(token_json, dict):
            token_json = json.dumps(token_json)

        # Проверяем, что это валидный JSON с полем token
        try:
            parsed = json.loads(token_json)
        except (json.JSONDecodeError, ValueError):
            logger.error(f"NaloGO: ответ на логин не JSON: {str(token_json)[:200]}")
            return None

        if not parsed.get("token"):
            logger.error(f"NaloGO: в ответе нет поля token. Ключи: {list(parsed.keys())}")
            return None

        await save_nalogo_token(token_json, "")
        logger.info("NaloGO: успешный логин по ИНН+паролю, токен сохранён в БД")
        return token_json

    except Exception as e:
        logger.error(f"NaloGO: ошибка логина по ИНН+паролю: {e}", exc_info=True)
        return None


async def _get_authenticated_client():
    """
    Возвращает (client, token_json) с валидным токеном.
    Логика:
      1. Пробуем токен из БД через authenticate.
      2. Если протух — refresh.
      3. Если refresh не работает — логин по ИНН+паролю.
    """
    from admin_app import get_nalogo_token, save_nalogo_token

    stored_json, _ = await get_nalogo_token()

    client = Client(device_id=DEVICE_ID)

    # ---------- Шаг 1: пробуем то, что есть в БД ----------
    if stored_json:
        try:
            await client.auth_provider.set_token(stored_json)
            await client.authenticate(stored_json)
            logger.info("NaloGO: используем токен из БД")
            return client, stored_json
        except Exception as e:
            logger.warning(f"NaloGO: токен из БД не работает ({e}) — пробуем refresh")

        # ---------- Шаг 2: refresh ----------
        try:
            parsed = json.loads(stored_json)
            refresh_token = parsed.get("refreshToken") if isinstance(parsed, dict) else None
            if refresh_token:
                new_data = await client.auth_provider.refresh(refresh_token)
                if new_data:
                    new_json = json.dumps(new_data) if isinstance(new_data, dict) else new_data
                    # Проверяем, что в новом токене есть поле token
                    try:
                        new_parsed = json.loads(new_json)
                        if new_parsed.get("token"):
                            await save_nalogo_token(new_json, "")
                            await client.auth_provider.set_token(new_json)
                            await client.authenticate(new_json)
                            logger.info("NaloGO: токен обновлён через refresh")
                            return client, new_json
                    except (json.JSONDecodeError, ValueError):
                        pass
        except Exception as e:
            logger.warning(f"NaloGO: refresh не удался ({e}) — логинимся по ИНН+паролю")

    # ---------- Шаг 3: логин по ИНН+паролю ----------
    logger.info("NaloGO: логинюсь по ИНН+паролю")
    new_json = await _login_by_password()
    if not new_json:
        logger.error("NaloGO: не удалось залогиниться. Проверь NALOGO_INN и NALOGO_PASSWORD.")
        return None, None

    client2 = Client(device_id=DEVICE_ID)
    try:
        await client2.auth_provider.set_token(new_json)
        await client2.authenticate(new_json)
        return client2, new_json
    except Exception as e:
        logger.error(f"NaloGO: не удалось использовать свежий токен: {e}")
        return None, None


async def request_sms_code(phone: str) -> dict:
    """SMS-вход больше не используется, но оставлен на всякий случай."""
    from admin_app import save_nalogo_challenge
    try:
        client = Client(device_id=DEVICE_ID)
        challenge = await client.create_phone_challenge(phone)
        challenge_token = challenge.get("challengeToken") if isinstance(challenge, dict) else getattr(challenge, "challenge_token", None)
        if not challenge_token:
            return {"ok": False, "error": f"Нет challengeToken в ответе: {challenge}"}
        await save_nalogo_challenge(phone, challenge_token)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка запроса SMS: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def confirm_sms_code(code: str) -> dict:
    """SMS-вход больше не используется."""
    from admin_app import get_nalogo_challenge, save_nalogo_token
    try:
        phone, challenge_token = await get_nalogo_challenge()
        if not phone or not challenge_token:
            return {"ok": False, "error": "Сначала запроси код заново"}
        client = Client(device_id=DEVICE_ID)
        token_json = await client.create_new_access_token_by_phone(phone, challenge_token, code)
        if isinstance(token_json, dict):
            token_json = json.dumps(token_json)
        try:
            parsed = json.loads(token_json)
        except (json.JSONDecodeError, ValueError) as e:
            return {"ok": False, "error": f"Ответ не JSON: {e}"}
        if not parsed.get("token"):
            return {"ok": False, "error": f"Нет поля token. Ключи: {list(parsed.keys())}"}
        await save_nalogo_token(token_json, "")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка подтверждения SMS: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def create_receipt_and_get_url(
    user_id: int,
    amount: float,
    payment_id: str = "",
    description: str = "Подписка на бота AI English US, 30 дней",
) -> dict | None:
    """Создаёт чек и скачивает изображение."""
    try:
        client, token_json = await _get_authenticated_client()
        if not client:
            return None

        bearer_token = _extract_bearer_token(token_json)
        if not bearer_token:
            logger.error(f"NaloGO: не удалось извлечь 'token' из JSON. Начало: {token_json[:120]}")
            return None

        income_api = client.income()
        result = await income_api.create(
            name=description,
            amount=Decimal(str(amount)),
            quantity=1,
        )

        receipt_uuid = result.get("approvedReceiptUuid") if isinstance(result, dict) else getattr(result, "approved_receipt_uuid", None)
        if not receipt_uuid:
            logger.error(f"Чек создан, но UUID не найден. result={result}")
            return None

        inn = NALOGO_INN
        if not inn:
            logger.error("NALOGO_INN не задан")
            return {"print_url": None, "image_bytes": None}
        print_url = f"https://lknpd.nalog.ru/api/v1/receipt/{inn}/{receipt_uuid}/print"
        logger.info(f"Собран print_url: {print_url}")

        async with httpx.AsyncClient(timeout=30) as http_client:
            resp = await http_client.get(
                print_url,
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
            if resp.status_code != 200:
                logger.error(f"Не удалось скачать изображение чека: {resp.status_code} — {resp.text[:200]}")
                return {"print_url": print_url, "image_bytes": None}

            image_bytes = resp.content
            if not (image_bytes.startswith(b'\x89PNG') or image_bytes.startswith(b'\xff\xd8')):
                logger.error(f"Скачанный файл не является изображением. Начало: {image_bytes[:20]}")
                return {"print_url": print_url, "image_bytes": None}

        logger.info(f"✅ Чек создан и изображение скачано для user {user_id}, uuid={receipt_uuid}")
        return {"print_url": print_url, "image_bytes": image_bytes}

    except Exception as e:
        logger.error(f"Ошибка создания чека для user {user_id}: {e}", exc_info=True)
        return None


async def cancel_receipt(receipt_url: str) -> bool:
    """Аннулирует чек в «Мой налог»."""
    try:
        parts = receipt_url.rstrip("/").split("/")
        if len(parts) < 2:
            logger.error(f"cancel_receipt: не могу разобрать URL: {receipt_url}")
            return False
        receipt_uuid = parts[-2]

        client, token_json = await _get_authenticated_client()
        if not client:
            return False

        bearer_token = _extract_bearer_token(token_json)
        if not bearer_token:
            return False

        async with httpx.AsyncClient(timeout=30) as http_client:
            resp = await http_client.post(
                "https://lknpd.nalog.ru/api/v1/income/cancel",
                headers={
                    "Authorization": f"Bearer {bearer_token}",
                    "Content-Type": "application/json",
                },
                json={"receiptUuid": receipt_uuid},
            )
            if resp.status_code in (200, 204):
                logger.info(f"✅ Чек {receipt_uuid} аннулирован")
                return True
            else:
                logger.error(f"Не удалось аннулировать чек: {resp.status_code} — {resp.text[:200]}")
                return False

    except Exception as e:
        logger.error(f"Ошибка аннулирования чека: {e}", exc_info=True)
        return False