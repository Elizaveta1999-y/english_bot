from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

# Список префиксов состояний, в которых голос НЕ нужен
VOICE_BLOCK_STATES = [
    "ReadingStates",
    "ListeningStates",
    "WritingStates",
    "GrammarStates",
    "WordsStates",
]

class ModeIsolationMiddleware(BaseMiddleware):
    """
    Блокирует голосовые сообщения в режимах, где голос не нужен (чтение, аудирование, письмо, грамматика, лексика).
    В режимах говорения, общения с AI, ролевых игр голос пропускается.
    """
    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Пропускаем callback-запросы
        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        # Проверяем, что это голосовое сообщение
        if event.voice:
            state: FSMContext = data.get("state")
            if state:
                current_state = await state.get_state()
                if current_state:
                    # Если состояние начинается с одного из блокируемых префиксов
                    for prefix in VOICE_BLOCK_STATES:
                        if current_state.startswith(prefix):
                            # Блокируем голосовое сообщение (не передаём дальше)
                            return
            # Если состояние не определено или не блокируемое – пропускаем
            return await handler(event, data)

        # Все остальные сообщения пропускаем
        return await handler(event, data)