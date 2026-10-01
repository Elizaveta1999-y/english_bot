import os
import io
import json
import logging
from decimal import Decimal
import httpx
from nalogo import Client
try:
    from nalogo.exceptions import UnauthorizedException
except ImportError:
    UnauthorizedException = Exception

logger = logging.getLogger(__name__)

DEVICE_ID = "english-bot-admin"
NALOGO_INN = os.getenv("NALOGO_INN") or os.getenv("NALOG_INN")
NALOGO_PASSWORD = os.getenv("NALOGO_PASSWORD") or os.getenv("NALOG_PASSWORD")


def _extract_bearer_token(token_json: str) -> str | None:
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
    from admin_app import save_nalogo_token

    if not NALOGO_INN or not NALOGO_PASSWORD:
        logger.error("NaloGO: NALOGO_INN или NALOGO_PASSWORD не заданы на Render!")
        return None

    try:
        client = Client(device_id=DEVICE_ID)
        token_json = await client.create_new_access_token(NALOGO_INN, NALOGO_PASSWORD)

        if not token_json:
            logger.error("NaloGO: create_new_access_token вернул пусто")
            return None

        if isinstance(token_json, dict):
            token_json = json.dumps(token_json, ensure_ascii=False)

        try:
            parsed = json.loads(token_json)
        except (json.JSONDecodeError, ValueError):
            logger.error(f"NaloGO: ответ не JSON: {str(token_json)[:200]}")
            return None

        if not parsed.get("token"):
            logger.error(f"NaloGO: нет поля token. Ключи: {list(parsed.keys())}")
            return None

        await save_nalogo_token(token_json, "")
        logger.info("NaloGO: логин по ИНН+паролю УСПЕШЕН, токен сохранён в БД")
        return token_json

    except Exception as e:
        logger.error(f"NaloGO: ошибка логина по ИНН+паролю: {e}", exc_info=True)
        return None


def _get_current_token_from_client(client) -> str | None:
    """Извлекает актуальный токен из клиента после операций (мог обновиться)."""
    try:
        auth_provider = getattr(client, "auth_provider", None)
        if not auth_provider:
            return None
        for attr in ("_token_json", "token_json", "_token", "token"):
            tok = getattr(auth_provider, attr, None)
            if tok:
                if isinstance(tok, dict):
                    return json.dumps(tok, ensure_ascii=False)
                if isinstance(tok, str) and tok.strip().startswith("{"):
                    return tok
        return None
    except Exception as e:
        logger.debug(f"NaloGO: не удалось извлечь токен из клиента: {e}")
        return None


async def _attempt_client(tj: str) -> Client:
    c = Client(device_id=DEVICE_ID)
    try:
        await c.auth_provider.set_token(tj)
    except Exception as e:
        logger.warning(f"NaloGO: set_token упал: {e}")
    try:
        await c.authenticate(tj)
    except Exception as e:
        logger.warning(f"NaloGO: authenticate упал: {e}")
    return c


async def _create_income(token_json: str, amount: float, description: str):
    """
    Пытается создать чек.
    Возвращает (result, fresh_token_json) или (None, None).
    fresh_token_json — актуальный токен (мог обновиться внутри библиотеки).
    """
    from admin_app import save_nalogo_token

    if token_json:
        client = await _attempt_client(token_json)
        try:
            result = await client.income().create(
                name=description,
                amount=Decimal(str(amount)),
                quantity=1,
            )
            fresh = _get_current_token_from_client(client) or token_json
            return result, fresh
        except UnauthorizedException as e:
            logger.warning(f"NaloGO: 401 с токеном из БД — пробую refresh. {e}")
            try:
                parsed = json.loads(token_json)
                rt = parsed.get("refreshToken") if isinstance(parsed, dict) else None
                if rt:
                    new_data = await client.auth_provider.refresh(rt)
                    if new_data:
                        new_json = json.dumps(new_data, ensure_ascii=False) if isinstance(new_data, dict) else new_data
                        await save_nalogo_token(new_json, "")
                        client2 = await _attempt_client(new_json)
                        result = await client2.income().create(
                            name=description,
                            amount=Decimal(str(amount)),
                            quantity=1,
                        )
                        fresh = _get_current_token_from_client(client2) or new_json
                        return result, fresh
            except Exception as e2:
                logger.warning(f"NaloGO: refresh не сработал: {e2}")
        except Exception as e:
            logger.error(f"NaloGO: ошибка income.create: {e}")

    logger.info("NaloGO: пробую логин по ИНН+паролю")
    new_json = await _login_by_password()
    if not new_json:
        return None, None

    client3 = await _attempt_client(new_json)
    try:
        result = await client3.income().create(
            name=description,
            amount=Decimal(str(amount)),
            quantity=1,
        )
        fresh = _get_current_token_from_client(client3) or new_json
        return result, fresh
    except Exception as e:
        logger.error(f"NaloGO: не удалось создать чек и после логина по паролю: {e}", exc_info=True)
        return None, None


async def create_receipt_and_get_url(
    user_id: int,
    amount: float,
    payment_id: str = "",
    description: str = "Подписка на бота AI English US, 30 дней",
) -> dict | None:
    from admin_app import get_nalogo_token, save_nalogo_token

    try:
        stored_json, _ = await get_nalogo_token()
        result, fresh_token = await _create_income(stored_json, amount, description)
        if not result:
            return None

        # Сохраняем свежий токен (мог обновиться в библиотеке)
        if fresh_token:
            await save_nalogo_token(fresh_token, "")

        receipt_uuid = result.get("approvedReceiptUuid") if isinstance(result, dict) else getattr(result, "approved_receipt_uuid", None)
        if not receipt_uuid:
            logger.error(f"Чек создан, но UUID не найден. result={result}")
            return None

        bearer_token = _extract_bearer_token(fresh_token) if fresh_token else None
        if not bearer_token:
            logger.error("Не удалось извлечь bearer из свежего токена")
            return {"print_url": None, "image_bytes": None}

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

            # Если 401 — перелогиниваемся и пробуем снова
            if resp.status_code == 401:
                logger.warning("NaloGO: 401 при скачивании — пробую перелогиниться")
                relogin = await _login_by_password()
                if relogin:
                    bearer2 = _extract_bearer_token(relogin)
                    if bearer2:
                        resp = await http_client.get(
                            print_url,
                            headers={"Authorization": f"Bearer {bearer2}"},
                        )

            if resp.status_code != 200:
                logger.error(f"Не удалось скачать чек: {resp.status_code} — {resp.text[:200]}")
                return {"print_url": print_url, "image_bytes": None}

            image_bytes = resp.content
            if not (image_bytes.startswith(b'\x89PNG') or image_bytes.startswith(b'\xff\xd8')):
                logger.error(f"Скачано не изображение: {image_bytes[:20]}")
                return {"print_url": print_url, "image_bytes": None}

        logger.info(f"✅ Чек создан и изображение скачано для user {user_id}, uuid={receipt_uuid}")
        return {"print_url": print_url, "image_bytes": image_bytes}

    except Exception as e:
        logger.error(f"Ошибка создания чека для user {user_id}: {e}", exc_info=True)
        return None


async def cancel_receipt(receipt_url: str) -> bool:
    try:
        parts = receipt_url.rstrip("/").split("/")
        if len(parts) < 2:
            logger.error(f"cancel_receipt: не могу разобрать URL: {receipt_url}")
            return False
        receipt_uuid = parts[-2]

        from admin_app import get_nalogo_token
        stored_json, _ = await get_nalogo_token()
        if not stored_json:
            return False

        bearer_token = _extract_bearer_token(stored_json)
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


async def request_sms_code(phone: str) -> dict:
    return {"ok": False, "error": "SMS-вход отключён. Используется авторизация по ИНН+паролю."}


async def confirm_sms_code(code: str) -> dict:
    return {"ok": False, "error": "SMS-вход отключён. Используется авторизация по ИНН+паролю."}