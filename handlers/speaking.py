from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from data.users import set_user_state, get_user_state
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