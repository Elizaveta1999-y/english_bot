import os
import logging
from decimal import Decimal
from nalogo import Client

logger = logging.getLogger(__name__)

NALOGO_INN = os.getenv("NALOGO_INN")
NALOGO_PASSWORD = os.getenv("NALOGO_PASSWORD")
SESSION_FILE = "nalogo_session.json"


async def create_receipt_and_get_url(
    user_id: int,
    amount: float,
    payment_id: str = "",
    description: str = "Подписка на бота AI English US, 30 дней",
) -> str | None:
    """
    Создаёт чек в «Мой налог» и возвращает ссылку на него.
    Если не удалось — возвращает None.
    """
    if not NALOGO_INN or not NALOGO_PASSWORD:
        logger.error("NALOGO_INN или NALOGO_PASSWORD не заданы")
        return None

    try:
        # 1. Создаём клиент (без ИНН и пароля — только настройки)
        client = Client(
            storage_path=SESSION_FILE,
            device_id="english-bot-admin",
        )

        # 2. Получаем токен по ИНН/паролю
        token = await client.create_new_access_token(NALOGO_INN, NALOGO_PASSWORD)

        # 3. Активируем клиент
        await client.authenticate(token)

        # 4. Создаём чек
        income_api = client.income()
        result = await income_api.create(
            name=description,
            amount=Decimal(str(amount)),
            quantity=1,
        )

        # 5. Достаём UUID чека
        receipt_uuid = result.get("approvedReceiptUuid")
        if not receipt_uuid:
            logger.error(f"Чек создан, но UUID не найден. result={result}")
            return None

        # 6. Получаем ссылку для печати
        receipt_api = client.receipt()
        print_url = receipt_api.print_url(receipt_uuid)

        if not print_url:
            logger.error(f"UUID получен, но ссылка не сгенерирована. uuid={receipt_uuid}")
            return None

        logger.info(f"✅ Чек создан для user {user_id}, uuid={receipt_uuid}, url={print_url}")
        return print_url

    except Exception as e:
        logger.error(f"Ошибка создания чека для user {user_id}: {e}", exc_info=True)
        return None