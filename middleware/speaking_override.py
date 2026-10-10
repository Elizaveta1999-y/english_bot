from typing import Callable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from data.users import get_user_state, set_user_state
from handlers.start import show_main_menu


class SpeakingOverrideMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        bot_obj = None
        chat_id = None

        if isinstance(event, Message):
            user_id = event.from_user.id
            bot_obj = event.bot
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            bot_obj = event.bot
            chat_id = event.message.chat.id if event.message else None
        else:
            return await handler(event, data)

        if not user_id or not bot_obj or chat_id is None:
            return await handler(event, data)

        user_state = get_user_state(user_id)
        if user_state.get("mode") != "speaking_active":
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            if event.data.startswith((
                "show_text_",
                "translate_text_",
                "show_original_",
                "hide_text_",
                "show_feedback_confirm",
                "continue_speaking",
                "start_",
                "support",
                "subscription",
                "agreement",
                "profile_menu",
                "profile_",
                "back_to_main_menu",
                "back_to_profile",
                "back_to_main",
            )):
                return await handler(event, data)

            if event.data == "back_to_main":
                user_state["mode"] = ""
                user_state["keyboard_hidden"] = True
                user_state["pending_feedback"] = None
                user_state["feedback_prompt_msg_id"] = None
                user_state["speaking_history"] = []
                set_user_state(user_id, user_state)
                await bot_obj.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())
                await show_main_menu(event.message, edit=False)
                return
            return

        if event.voice:
            return await handler(event, data)

        if event.text:
            allowed_commands = ["/support", "/subscription", "/agreement", "/start"]

            if event.text.startswith('/'):
                if event.text in allowed_commands:
                    return await handler(event, data)
                user_state["mode"] = ""
                user_state["keyboard_hidden"] = True
                user_state["pending_feedback"] = None
                user_state["feedback_prompt_msg_id"] = None
                user_state["speaking_history"] = []
                set_user_state(user_id, user_state)
                await bot_obj.send_message(chat_id, "Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
                await show_main_menu(event, edit=False)
                return

            if event.text == "🏠 Главное меню":
                user_state["mode"] = ""
                user_state["keyboard_hidden"] = True
                user_state["pending_feedback"] = None
                user_state["feedback_prompt_msg_id"] = None
                user_state["speaking_history"] = []
                set_user_state(user_id, user_state)
                await bot_obj.send_message(chat_id, "Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
                await show_main_menu(event, edit=False)
                return

            if event.text == "📊 Я всё! Фидбек":
                return await handler(event, data)

            return await handler(event, data)

        await bot_obj.send_message(chat_id, "Запишите и отправьте голосовое сообщение.")
        return