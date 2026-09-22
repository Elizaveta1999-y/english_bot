import os
import io
import logging
from decimal import Decimal
import qrcode
from nalogo import Client

logger = logging.getLogger(__name__)

DEVICE_ID = "english-bot-admin"


async def request_sms_code(phone: str) -> dict:
    """Запрашивает SMS-код у «Мой налог». Сохраняет challengeToken в БД."""
    from admin_app import save_nalogo_challenge
    try:
        client = Client(device_id=DEVICE_ID)

        challenge = await client.create_phone_challenge(phone)
        logger.info(f"SMS-код запрошен для {phone}")

        challenge_token = challenge.get("challengeToken")
        if not challenge_token:
            return {"ok": False, "error": f"Нет challengeToken в ответе: {challenge}"}

        await save_nalogo_challenge(phone, challenge_token)
        return {"ok": True}

    except Exception as e:
        logger.error(f"Ошибка запроса SMS: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def confirm_sms_code(code: str) -> dict:
    """Подтверждает SMS-код и сохраняет токен в БД."""
    from admin_app import get_nalogo_challenge, save_nalogo_token
    try:
        phone, challenge_token = await get_nalogo_challenge()
        if not phone or not challenge_token:
            return {"ok": False, "error": "Сначала запроси код заново"}

        client = Client(device_id=DEVICE_ID)

        token = await client.create_new_access_token_by_phone(
            phone, challenge_token, code
        )
        logger.info("Токен получен по SMS")

        access_token = token.get("accessToken") if isinstance(token, dict) else token
        refresh_token = token.get("refreshToken", "") if isinstance(token, dict) else ""

        if not access_token:
            return {"ok": False, "error": f"Токен пустой: {token}"}

        await save_nalogo_token(access_token, refresh_token)
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
    Создаёт чек в «Мой налог».
    Возвращает {"print_url": str, "qr_image": bytes} или None.
    """
    from admin_app import get_nalogo_token

    try:
        client = Client(device_id=DEVICE_ID)

        access_token, refresh_token = await get_nalogo_token()
        if not access_token:
            logger.error("NaloGO: нет токена в БД. Зайди на /nalog-login и авторизуйся по SMS.")
            return None

        try:
            await client.authenticate(access_token)
        except Exception as e:
            logger.error(f"NaloGO: токен из БД недействителен: {e}. Авторизуйся заново через /nalog-login")
            return None

        income_api = client.income()
        result = await income_api.create(
            name=description,
            amount=Decimal(str(amount)),
            quantity=1,
        )

        receipt_uuid = result.get("approvedReceiptUuid")
        if not receipt_uuid:
            logger.error(f"Чек создан, но UUID не найден. result={result}")
            return None

        receipt_api = client.receipt()
        print_url = receipt_api.print_url(receipt_uuid)
        if not print_url:
            logger.error(f"UUID получен, но ссылка не сгенерирована. uuid={receipt_uuid}")
            return None

        # Генерируем QR-код из ссылки на чек
        qr = qrcode.QRCode(version=None, box_size=10, border=2)
        qr.add_data(print_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_bytes = buf.getvalue()

        logger.info(f"✅ Чек создан для user {user_id}, uuid={receipt_uuid}, QR готов")
        return {"print_url": print_url, "qr_image": qr_bytes}

    except Exception as e:
        logger.error(f"Ошибка создания чека для user {user_id}: {e}", exc_info=True)
        return None