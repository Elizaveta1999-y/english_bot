from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from states.reading_states import ReadingStates

class ModeIsolationMiddleware(BaseMiddleware):
    """
    Middleware для изоляции режимов.
    Если пользователь находится в состоянии чтения (ReadingStates),
    все текстовые и голосовые сообщения блокируются (не передаются в другие обработчики).
    Callback-запросы пропускаются (они обрабатываются в своих роутерах).
    """
    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Пропускаем callback-запросы (они идут только в свои обработчики)
        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        # Для сообщений проверяем состояние
        state: FSMContext = data.get("state")
        if state:
            current_state = await state.get_state()
            # Если состояние принадлежит режиму чтения – блокируем
            if current_state and current_state.startswith("ReadingStates"):
                # Пропускаем только команды, которые должны работать всегда
                if event.text and event.text.startswith("/"):
                    # Команды /start, /support, /subscription должны работать
                    # Можно пропустить их (они обрабатываются в своих файлах)
                    pass
                else:
                    # Блокируем любое другое сообщение
                    return  # Не передаём дальше
        # Если не в режиме чтения или команда – передаём дальше
        return await handler(event, data)