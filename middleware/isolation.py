from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

class ModeIsolationMiddleware(BaseMiddleware):
    """
    Блокирует голосовые сообщения в режиме чтения (ReadingStates).
    Все остальные сообщения пропускаются.
    """
    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Callback-запросы всегда пропускаем
        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        # Блокируем только голосовые сообщения в режиме чтения
        if event.voice:
            state: FSMContext = data.get("state")
            if state:
                current_state = await state.get_state()
                if current_state and current_state.startswith("ReadingStates"):
                    # Голос в режиме чтения не нужен – блокируем
                    return
        # Всё остальное пропускаем
        return await handler(event, data)