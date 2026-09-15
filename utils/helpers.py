async def with_thinking(message, coro, thinking_text="🤔 Думаю..."):
    """
    Отправляет 'Думаю...', ждёт выполнения coro, заменяет 'Думаю...' на результат.
    Возвращает (thinking_msg, result).
    """
    thinking_msg = await message.answer(thinking_text)
    try:
        result = await coro
    except Exception:
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        raise
    return thinking_msg, result