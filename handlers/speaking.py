from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import set_user_state, get_user_state
from services.deepseek import chat

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
async def start_speaking(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Woman Voice", callback_data="speaking_voice_woman"),
         InlineKeyboardButton(text="👨 Man Voice", callback_data="speaking_voice_man")]
    ])
    await callback.message.edit_text(SPEAKING_INTRO_TEXT, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("speaking_voice_"))
async def select_voice(callback: CallbackQuery):
    user_id = callback.from_user.id
    voice = callback.data.split("_")[2]  # "woman" или "man"
    user_state = get_user_state(user_id)
    user_state["speaking_voice"] = voice
    user_state["mode"] = "speaking_active"
    if "history" not in user_state:
        user_state["history"] = []
    set_user_state(user_id, user_state)

    # Удаляем сообщение с выбором голоса
    await callback.message.delete()
    
    # Клавиатура для режима
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