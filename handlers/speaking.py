from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from data.users import set_user_state, get_user_state
from services.deepseek import chat
from states.speaking_states import SpeakingStates
from speaking.services.ai import process_voice_message

router = Router()

SPEAKING_INTRO_TEXT = (
    "🎤 <b>Speaking: говори свободно</b>\n\n"
    "Нажми и общайся на любые темы — как в реальной жизни.\n"
    "ИИ понимает акцент и естественную речь.\n"
    "Мгновенная коррекция грамматики, лексики и произношения с понятными объяснениями.\n\n"
    "🔊 <b>Слушай, говори и получай фидбек в реальном времени.</b>\n\n"
    "Выберите голос помощника:"
)

@router.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Woman Voice", callback_data="speaking_voice_woman"),
         InlineKeyboardButton(text="👨 Man Voice", callback_data="speaking_voice_man")]
    ])
    await callback.message.edit_text(SPEAKING_INTRO_TEXT, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("speaking_voice_"))
async def select_voice(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    voice = callback.data.split("_")[2]  # "woman" или "man"
    user_state = get_user_state(user_id)
    user_state["speaking_voice"] = voice
    user_state["mode"] = "speaking_active"
    if "history" not in user_state:
        user_state["history"] = []
    set_user_state(user_id, user_state)

    await state.set_state(SpeakingStates.waiting_for_voice)

    await callback.message.delete()
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Я всё! Фидбек")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )
    await callback.message.answer(
        "🗣️ <b>Говори развёрнуто – так эффективнее для изучения!</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(SpeakingStates.waiting_for_voice, F.text == "📊 Я всё! Фидбек")
async def feedback_button(message: Message, state: FSMContext):
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

@router.message(SpeakingStates.waiting_for_voice, F.text == "🏠 Главное меню")
async def exit_to_main_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = None
    set_user_state(user_id, user_state)
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)

# ========== НОВЫЙ ОБРАБОТЧИК ТЕКСТА В РЕЖИМЕ SPEAKING ==========
@router.message(SpeakingStates.waiting_for_voice, F.text)
async def handle_speaking_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    
    # Проверяем, что мы действительно в режиме Speaking
    if user_state.get("mode") != "speaking_active":
        return

    # Если текст - служебная кнопка, пропускаем (они обработаны выше)
    if message.text in ["📊 Я всё! Фидбек", "🏠 Главное меню"]:
        return

    # Обрабатываем текст через ИИ
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    ai_response = await process_voice_message(user_id, message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    sent = await message.answer(ai_response, reply_markup=keyboard)
    
    # Сохраняем историю
    from handlers.voice import last_text_response as global_last_text_response
    global_last_text_response[user_id] = {"text": ai_response, "translation": None, "message_id": sent.message_id}
    
    history = user_state.get("history", [])
    history.append({"role": "user", "text": message.text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

# Обработчик голосовых сообщений (уже есть в voice.py, но оставим здесь на всякий случай)
@router.message(SpeakingStates.waiting_for_voice, F.voice)
async def handle_voice_in_speaking(message: Message, state: FSMContext):
    # Здесь можно оставить пустой, если голос обрабатывается в voice.py
    # Но чтобы не дублировать, просто вызовем обработчик из voice.py
    # Импортируем и вызываем
    from handlers.voice import handle_voice
    await handle_voice(message)