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

    payment_id — уникальный ID платежа из ЮKassa. Передаётся в API
    как operationUniqueId, чтобы ФНС отсекла дубли при повторном вебхуке.
    """
    if not NALOGO_INN or not NALOGO_PASSWORD:
        logger.error("NALOGO_INN или NALOGO_PASSWORD не заданы")
        return None

    client = None
    try:
        # Создаём клиент с сохранением сессии в файл
        client = Client(
            inn=NALOGO_INN,
            password=NALOGO_PASSWORD,
            device_id="english-bot-admin",
        )

        # Аутентификация (может восстановить сессию из файла)
        try:
            await client.authenticate()
        except Exception as auth_err:
            logger.error(f"Ошибка авторизации в «Мой налог»: {auth_err}", exc_info=True)
            return None

        # Готовим параметры чека
        receipt_kwargs = {
            "name": description,
            "amount": Decimal(str(amount)),
            "quantity": 1,
        }
        if payment_id:
            receipt_kwargs["operation_unique_id"] = payment_id

        # Создаём чек. Если библиотека не поддерживает operation_unique_id —
        # повторяем без него.
        try:
            receipt = await client.create_receipt(**receipt_kwargs)
        except TypeError:
            logger.warning("nalogo не поддерживает operation_unique_id, создаю без него")
            receipt_kwargs.pop("operation_unique_id", None)
            receipt = await client.create_receipt(**receipt_kwargs)

        # Извлекаем ссылку на печать — у разных версий библиотеки поле может называться по-разному
        print_url = _extract_print_url(receipt)
        if not print_url:
            logger.error(f"Чек создан, но ссылка не найдена. receipt={receipt!r}")
            return None

        logger.info(f"✅ Чек создан для user {user_id}, payment_id={payment_id}, url={print_url}")
        return print_url

    except Exception as e:
        logger.error(f"Ошибка создания чека для user {user_id}: {e}", exc_info=True)
        return None
    finally:
        # Закрываем клиент, если есть метод close
        if client is not None:
            try:
                close = getattr(client, "close", None)
                if close:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
            except Exception:
                pass


def _extract_print_url(receipt) -> str | None:
    """Пытается достать ссылку на печать из ответа API."""
    # Вариант 1: атрибуты объекта
    for attr in ("print_url", "printUrl", "print_link", "printLink"):
        url = getattr(receipt, attr, None)
        if url:
            return str(url)

    # Вариант 2: словарь внутри объекта
    for dict_attr in ("data", "raw", "response"):
        data = getattr(receipt, dict_attr, None)
        if isinstance(data, dict):
            for key in ("printUrl", "print_url", "printLink", "print_link"):
                if data.get(key):
                    return str(data[key])

    # Вариант 3: сам объект — словарь
    if isinstance(receipt, dict):
        for key in ("printUrl", "print_url", "printLink", "print_link"):
            if receipt.get(key):
                return str(receipt[key])

    return None