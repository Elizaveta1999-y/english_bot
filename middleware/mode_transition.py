import logging
from typing import Callable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from data.users import get_user_state, set_user_state

logger = logging.getLogger(__name__)

# Callback'и, при которых нужно чистить текущий активный режим
TRANSITION_CALLBACKS = (
    "start_speaking",
    "start_reading",
    "start_roleplay",
    "start_grammar",
    "start_words",
    "start_listening",
    "start_writing",
    "start_govorenie",
    "profile_menu",
)


class ModeTransitionMiddleware(BaseMiddleware):
    """Глобальная очистка текущего режима перед переходом в другой."""

    async def __call__(
        self,
        handler: Callable,
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Работаем только с callback'ами
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        # Работаем только при переходах между режимами
        if event.data not in TRANSITION_CALLBACKS:
            return await handler(event, data)

        user_id = event.from_user.id
        user_state = get_user_state(user_id)
        mode = user_state.get("mode")

        # Если режим не активен – ничего не чистим
        if not mode:
            return await handler(event, data)

        chat_id = event.message.chat.id if event.message else None
        logger.info(f"[ModeTransition] Переход из mode={mode} для user={user_id}")

        try:
            state = data.get("state")

            # --- ГРАММАТИКА ---
            if mode == "grammar_active":
                if state:
                    sdata = await state.get_data()
                    for key in ("task_msg_id", "progress_msg_id", "revision_msg_id", "revision_header_msg_id"):
                        msg_id = sdata.get(key)
                        if msg_id and chat_id:
                            try:
                                await event.bot.edit_message_reply_markup(
                                    chat_id=chat_id, message_id=msg_id, reply_markup=None
                                )
                            except Exception:
                                pass
                    await state.clear()

            # --- ЛЕКСИКА ---
            elif mode == "words_active":
                from handlers.words import user_message_ids, user_sessions, remove_buttons_from_messages
                if user_id in user_message_ids and chat_id:
                    msg_ids = list(user_message_ids[user_id].values())
                    await remove_buttons_from_messages(event.bot, chat_id, msg_ids)
                    user_message_ids[user_id] = {}
                user_sessions.pop(user_id, None)
                if state:
                    await state.clear()

            # --- АУДИРОВАНИЕ ---
            elif mode == "listening_active":
                from handlers.listening import clear_user_buttons
                if chat_id:
                    await clear_user_buttons(user_id, event.bot, chat_id)
                if state:
                    await state.clear()

            # --- ПИСЬМО ---
            elif mode == "writing_active":
                if state:
                    sdata = await state.get_data()
                    for key in ("progress_msg_id", "last_task_msg_id"):
                        msg_id = sdata.get(key)
                        if msg_id and chat_id:
                            try:
                                await event.bot.edit_message_reply_markup(
                                    chat_id=chat_id, message_id=msg_id, reply_markup=None
                                )
                            except Exception:
                                pass
                    await state.clear()

            # --- ГОВОРЕНИЕ ---
            elif mode == "govorenie_active":
                if state:
                    sdata = await state.get_data()
                    for key in ("progress_msg_id", "last_task_msg_id"):
                        msg_id = sdata.get(key)
                        if msg_id and chat_id:
                            try:
                                await event.bot.edit_message_reply_markup(
                                    chat_id=chat_id, message_id=msg_id, reply_markup=None
                                )
                            except Exception:
                                pass
                    await state.clear()

            # --- SPEAKING ---
            elif mode == "speaking_active":
                kb_id = user_state.get("speaking_keyboard_msg_id")
                if kb_id and chat_id:
                    try:
                        await event.bot.delete_message(chat_id, kb_id)
                    except Exception:
                        pass
                    user_state.pop("speaking_keyboard_msg_id", None)
                if state:
                    await state.clear()

            # --- ROLEPLAY ---
            elif mode == "roleplay_active":
                kb_id = user_state.get("reply_keyboard_msg_id")
                if kb_id and chat_id:
                    try:
                        await event.bot.delete_message(chat_id, kb_id)
                    except Exception:
                        pass
                    user_state.pop("reply_keyboard_msg_id", None)
                keys_to_remove = [k for k in list(user_state.keys()) if k.startswith("roleplay")]
                for k in keys_to_remove:
                    user_state.pop(k, None)
                if state:
                    await state.clear()

            # --- СБРОС ФЛАГА РЕЖИМА ---
            user_state["mode"] = ""
            set_user_state(user_id, user_state)
            logger.info(f"[ModeTransition] Режим {mode} очищен")

        except Exception as e:
            logger.error(f"[ModeTransition] Ошибка очистки: {e}", exc_info=True)

        # Передаём управление дальше (в роутеры)
        return await handler(event, data)