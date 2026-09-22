import os
import io
import json
import logging
from decimal import Decimal
import httpx
from nalogo import Client

logger = logging.getLogger(__name__)

DEVICE_ID = "english-bot-admin"


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


async def _get_authenticated_client():
    """
    Возвращает (client, token_json) с валидным токеном.
    Если токен протух/протухает — делает refresh через auth_provider,
    сохраняет новый JSON в БД.
    """
    from admin_app import get_nalogo_token, save_nalogo_token

    stored_json, _ = await get_nalogo_token()
    if not stored_json:
        logger.error("NaloGO: нет токена в БД. Зайди на /nalog-login.")
        return None, None

    client = Client(device_id=DEVICE_ID)

    # 1. Устанавливаем токен в auth_provider, чтобы он знал, с чем работать
    try:
        await client.auth_provider.set_token(stored_json)
    except Exception as e:
        logger.error(f"NaloGO: set_token упал: {e}. Нужна переавторизация.")
        return None, None

    # 2. Проверяем, протух ли / протухает ли — если да, делаем refresh
    try:
        need_refresh = False
        try:
            need_refresh = client.auth_provider.is_token_expiring()
        except Exception:
            pass

        if need_refresh:
            logger.info("NaloGO: токен протухает — делаю refresh")
            parsed = json.loads(stored_json)
            refresh_token = parsed.get("refreshToken") if isinstance(parsed, dict) else None
            if not refresh_token:
                logger.error("NaloGO: нет refreshToken в JSON. Нужна переавторизация.")
                return None, None

            new_data = await client.auth_provider.refresh(refresh_token)
            if not new_data:
                logger.error("NaloGO: refresh вернул пусто. Нужна переавторизация.")
                return None, None
            new_json = json.dumps(new_data) if isinstance(new_data, dict) else new_data
            await save_nalogo_token(new_json, "")
            await client.auth_provider.set_token(new_json)
            stored_json = new_json
            logger.info("NaloGO: токен обновлён через refresh")

    except Exception as e:
        logger.warning(f"NaloGO: проверка/refresh не удалась ({e}), пробую authenticate как есть")

    # 3. Аутентифицируемся
    try:
        await client.authenticate(stored_json)
    except Exception as e:
        logger.error(f"NaloGO: authenticate не прошёл: {e}. Пробую refresh...")
        # Последняя попытка — прямой refresh
        try:
            parsed = json.loads(stored_json)
            refresh_token = parsed.get("refreshToken") if isinstance(parsed, dict) else None
            if not refresh_token:
                return None, None
            new_data = await client.auth_provider.refresh(refresh_token)
            if not new_data:
                return None, None
            new_json = json.dumps(new_data) if isinstance(new_data, dict) else new_data
            await save_nalogo_token(new_json, "")
            await client.auth_provider.set_token(new_json)
            await client.authenticate(new_json)
            stored_json = new_json
            logger.info("NaloGO: токен обновлён через refresh (после ошибки auth)")
        except Exception as e2:
            logger.error(f"NaloGO: refresh тоже упал: {e2}. Нужна переавторизация через /nalog-login.")
            return None, None

    return client, stored_json


async def request_sms_code(phone: str) -> dict:
    """Запрашивает SMS-код у «Мой налог». Сохраняет challengeToken в БД."""
    from admin_app import save_nalogo_challenge
    try:
        client = Client(device_id=DEVICE_ID)

        challenge = await client.create_phone_challenge(phone)
        logger.info(f"SMS-код запрошен для {phone}")

        challenge_token = challenge.get("challengeToken") if isinstance(challenge, dict) else getattr(challenge, "challenge_token", None)
        if not challenge_token:
            return {"ok": False, "error": f"Нет challengeToken в ответе: {challenge}"}

        await save_nalogo_challenge(phone, challenge_token)
        return {"ok": True}

    except Exception as e:
        logger.error(f"Ошибка запроса SMS: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def confirm_sms_code(code: str) -> dict:
    """Подтверждает SMS-код и сохраняет ПОЛНЫЙ JSON-токен в БД."""
    from admin_app import get_nalogo_challenge, save_nalogo_token
    try:
        phone, challenge_token = await get_nalogo_challenge()
        if not phone or not challenge_token:
            return {"ok": False, "error": "Сначала запроси код заново"}

        client = Client(device_id=DEVICE_ID)

        token_json = await client.create_new_access_token_by_phone(
            phone, challenge_token, code
        )
        logger.info(f"Ответ auth типа {type(token_json).__name__}, начало: {str(token_json)[:120]}")

        try:
            parsed = json.loads(token_json)
        except (json.JSONDecodeError, ValueError) as e:
            return {"ok": False, "error": f"Ответ auth не JSON: {e}. Ответ: {str(token_json)[:200]}"}

        token_value = parsed.get("token") if isinstance(parsed, dict) else None
        if not token_value:
            return {"ok": False, "error": f"Нет поля 'token' в JSON. Ключи: {list(parsed.keys()) if isinstance(parsed, dict) else type(parsed)}"}

        await save_nalogo_token(token_json, "")
        logger.info(f"Токен сохранён. Начало JWT: {token_value[:30]}...")
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
    """
    Создаёт чек в «Мой налог» и скачивает изображение чека.
    Возвращает {"print_url": str, "image_bytes": bytes} или None.
    """
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

        # Собираем URL вручную (client.receipt() требует profile, которого нет)
        # ВАЖНО: путь с /v1/, иначе API вернёт 404
        inn = os.getenv("NALOGO_INN") or os.getenv("NALOG_INN")
        if not inn:
            logger.error("NALOGO_INN не задан в переменных окружения")
            return {"print_url": None, "image_bytes": None}
        print_url = f"https://lknpd.nalog.ru/api/v1/receipt/{inn}/{receipt_uuid}/print"
        logger.info(f"Собран print_url: {print_url}")

        # Скачиваем картинку, используя bearer_token
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
                logger.error(f"Скачанный файл не является изображением. Начинается с: {image_bytes[:20]}")
                return {"print_url": print_url, "image_bytes": None}

        logger.info(f"✅ Чек создан и изображение скачано для user {user_id}, uuid={receipt_uuid}")
        return {"print_url": print_url, "image_bytes": image_bytes}

    except Exception as e:
        logger.error(f"Ошибка создания чека для user {user_id}: {e}", exc_info=True)
        return None
