import logging
from aiogram import BaseMiddleware
from aiogram.types import Message, ReplyKeyboardRemove
from data.users import get_user_state, set_user_state

logger = logging.getLogger(__name__)


class TutorGuardMiddleware(BaseMiddleware):
    """
    Ловит все сообщения, когда пользователь в режиме Наставник.
    - Голосовые пропускает дальше.
    - Кнопки Наставника (🏠 / 🧠) пропускает дальше.
    - Команды (/start, /subscription и др.) — завершает сессию и пропускает дальше.
    - Всё остальное (текст, фото, стикеры) — просит записать голосовое.
    """

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id
        user_state = get_user_state(user_id)

        if user_state.get("mode") != "tutor_active":
            return await handler(event, data)

        # Голосовое — пропускаем как есть
        if event.voice:
            return await handler(event, data)

        text = event.text or ""

        # Кнопки Наставника — пропускаем
        if text in ("🏠 Главное меню", "🧠 Память"):
            return await handler(event, data)

        # Команды — завершаем сессию и пропускаем дальше (команда обработается своим хендлером)
        if text.startswith("/"):
            print(f">>> TUTOR GUARD: команда {text} — завершаем сессию", flush=True)

            try:
                from handlers.tutor import finalize_tutor_session
                await finalize_tutor_session(
                    event.bot, event.chat.id, user_id,
                    silent=True, count_session=False
                )
            except Exception as e:
                logger.error(f"TutorGuard: ошибка финализации: {e}")

            # Очищаем mode и FSM state
            user_state = get_user_state(user_id)
            user_state["mode"] = ""
            user_state.pop("tutor_keyboard_msg_id", None)
            set_user_state(user_id, user_state)

            state = data.get("state")
            if state:
                try:
                    await state.clear()
                except Exception:
                    pass

            # Скрываем reply-клавиатуру + сообщение
            try:
                await event.answer("Урок завершен.", reply_markup=ReplyKeyboardRemove())
            except Exception:
                pass

            # Пропускаем дальше — команда обработается своим хендлером
            return await handler(event, data)

        # Всё остальное — просим голосовое
        print(">>> TUTOR GUARD: не-голосовое — просим голосовое", flush=True)
        await event.answer("Запиши голосовое сообщение.")
        return