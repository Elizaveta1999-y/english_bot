from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import set_user_state, get_user_state, add_to_history
from services.deepseek import chat
from speaking.services.ai import process_voice_message, process_roleplay_message

router = Router()
last_text_response = {}

@router.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_state(user_id, {"mode": "speaking_active", "history": []})
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Я всё! Фидбек")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )
    await callback.message.answer(
        "🎤 <b>Голосовой режим активирован!</b>\n\nГовори развёрнуто – так эффективнее для изучения! 🗣️",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@router.message(F.text == "📊 Я всё! Фидбек")
async def feedback_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        await message.answer("Фидбек доступен только в режиме Speaking.")
        return
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("Вы ещё не общались. Отправьте несколько голосовых сообщений.")
        return
    conversation = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    prompt = (
        "Ты учитель английского. Дай короткий фидбек (до 5 предложений) на русском языке. "
        "Сначала похвали, потом перечисли основные ошибки (с исправлениями), дай совет. "
        "Используй HTML-теги <b> и <i>. Добавь смайлики.\n\n"
        f"Диалог:\n{conversation}"
    )
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    feedback = chat(prompt, max_tokens=500, temperature=0.5)
    if len(feedback) > 1000:
        feedback = feedback[:1000] + "..."
    await message.answer(f"📊 <b>Ваш фидбек</b>:\n\n{feedback}", parse_mode="HTML")

# Общий обработчик текста для режимов Speaking и RolePlay (не для кастомных сценариев)
@router.message(F.text)
async def text_in_speaking_or_roleplay(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    # Если ожидаем кастомный сценарий – не обрабатываем здесь (этот случай уже в roleplay.py)
    if user_state.get("awaiting_custom_scenario"):
        return
    # Служебные кнопки – пропускаем, они обрабатываются в других хендлерах
    if message.text in ["📊 Я всё! Фидбек", "🏠 Главное меню", "💡 Что ответить?", "📊 Завершить диалог"]:
        return
    if mode in ("speaking_active", "roleplay_active"):
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        if mode == "roleplay_active":
            ai_response = await process_roleplay_message(user_id, message.text)
        else:
            ai_response = await process_voice_message(user_id, message.text)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
        ])
        sent = await message.answer(ai_response, reply_markup=keyboard)
        # Сохраняем в last_text_response для кнопки перевода
        from handlers.voice import last_text_response as global_last_text_response
        global_last_text_response[user_id] = {"text": ai_response, "translation": None, "message_id": sent.message_id}
        history = user_state.get("history", [])
        history.append({"role": "user", "text": message.text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)