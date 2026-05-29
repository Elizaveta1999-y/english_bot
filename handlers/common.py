from aiogram import Router, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import get_user_state, set_user_state, add_to_history
from speaking.services.ai import process_voice_message, process_roleplay_message
from handlers.voice import last_text_response

router = Router()

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    from handlers.start import start_handler
    await start_handler(message)

# ОБЩИЙ ОБРАБОТЧИК ТЕКСТА (ДОЛЖЕН БЫТЬ ПОСЛЕДНИМ)
@router.message(F.text)
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    # Пропускаем служебные кнопки (они уже обработаны в своих роутерах)
    if message.text in ["📊 Я всё! Фидбек", "🏠 Главное меню", "💡 Что ответить?", "📊 Завершить диалог"]:
        return
    # Если ожидаем кастомный сценарий – не обрабатываем (обработает roleplay.py)
    if user_state.get("awaiting_custom_scenario"):
        return
    if mode in ("speaking_active", "roleplay_active"):
        # Если текст короткий или пустой – игнорируем
        if len(message.text.strip()) < 2:
            return
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        if mode == "roleplay_active":
            ai_response = await process_roleplay_message(user_id, message.text)
        else:
            ai_response = await process_voice_message(user_id, message.text)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
        ])
        sent = await message.answer(ai_response, reply_markup=keyboard)
        last_text_response[user_id] = {"text": ai_response, "translation": None, "message_id": sent.message_id}
        # Сохраняем историю
        history = user_state.get("history", [])
        history.append({"role": "user", "text": message.text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)