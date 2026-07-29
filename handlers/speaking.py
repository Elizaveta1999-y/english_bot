from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from data.users import set_user_state, get_user_state, set_user_mode
from services.deepseek import chat
from states.speaking_states import SpeakingStates

router = Router()

SPEAKING_INTRO_TEXT = (
    "🎤 <b>Speaking: говори свободно</b>\n\n"
    "Нажми и общайся на любые темы — как в реальной жизни.\n"
    "ИИ понимает акцент и естественную речь.\n"
    "Мгновенная коррекция грамматики, лексики и произношения с понятными объяснениями.\n\n"
    "🔊 <b>Слушай, говори и получай фидбек в реальном времени.</b>\n\n"
    "Выберите голос помощника:"
)

@router.callback_query(F.data == "start_speaking")
async def start_speaking(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Woman Voice", callback_data="speaking_voice_woman"),
         InlineKeyboardButton(text="👨 Man Voice", callback_data="speaking_voice_man")]
    ])
    await callback.message.edit_text(SPEAKING_INTRO_TEXT, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("speaking_voice_"))
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

# ---------- Обработчики кнопок (только в активном состоянии) ----------
@router.message(SpeakingStates.waiting_for_voice, F.text == "📊 Я всё! Фидбек")
async def show_feedback(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("history", [])
    if not history:
        await message.answer("Вы пока ничего не сказали. Начните разговор!", reply_markup=None)
        return

    # Формируем фидбек от ИИ
    history_text = "\n".join([f"{msg['role']}: {msg['text']}" for msg in history if msg['role'] in ['user', 'assistant']])
    prompt = (
        "Ты – языковой тренер. Проанализируй диалог пользователя с ИИ и дай краткий фидбек по:\n"
        "- грамматике (укажи 2-3 ошибки и правильные варианты)\n"
        "- лексике (есть ли повторения, предложи синонимы)\n"
        "- общему впечатлению (беглость, разнообразие)\n"
        "Будь конструктивным, обращайся на 'ты'.\n"
        f"Диалог:\n{history_text}"
    )
    try:
        feedback = await chat(prompt, max_tokens=400, temperature=0.5)
    except Exception as e:
        logger.error(f"Ошибка получения фидбека: {e}")
        await message.answer("Не удалось получить фидбек. Попробуйте позже.")
        return

    # Сбрасываем историю после фидбека
    user_state["history"] = []
    set_user_state(user_id, user_state)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗣️ Продолжить разговор", callback_data="continue_speaking")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await message.answer(f"📊 <b>Фидбек по вашему диалогу:</b>\n\n{feedback}", reply_markup=keyboard, parse_mode="HTML")
    await message.answer("Можете продолжить разговор или вернуться в меню.", reply_markup=None)

@router.message(SpeakingStates.waiting_for_voice, F.text == "🏠 Главное меню")
async def exit_speaking(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)

# ---------- Обработчик кнопки "Продолжить разговор" ----------
@router.callback_query(F.data == "continue_speaking")
async def continue_speaking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = "speaking_active"
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Я всё! Фидбек")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )
    await callback.message.answer(
        "🗣️ <b>Продолжаем разговор. Говорите!</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# ---------- Обработчик текстовых сообщений в режиме говорения (если пользователь пишет текст) ----------
@router.message(SpeakingStates.waiting_for_voice, F.text)
async def handle_speaking_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        return

    # Обрабатываем как голосовой, только без аудио
    from speaking.services.ai import process_voice_message
    ai_response = await process_voice_message(user_id, message.text)

    history = user_state.get("history", [])
    history.append({"role": "user", "text": message.text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    await message.answer(ai_response)

# ---------- Импорт logger для фидбека ----------
import logging
logger = logging.getLogger(__name__)