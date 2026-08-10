import logging
import os
import random
import re
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import set_user_state, get_user_state
from services.deepseek import chat
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from states.speaking_states import SpeakingStates
from handlers.voice import convert_to_opus, bot_texts
from handlers.start import show_main_menu

logger = logging.getLogger(__name__)
router = Router()

WOMAN_VOICE_ID = "8quEMRkSpwEaWBzHvTLv"
MAN_VOICE_ID = "3TStB8f3X3To0Uj5R7RK"

GREETINGS = [
    "Hey! Ready to practice?",
    "Hi there! Let's start.",
    "Hello! How are you today?",
    "Good to see you! Let's go.",
    "What's new? Let's talk.",
    "Alright, let's begin!",
    "Hi! Just say something.",
    "Hey! Feeling confident today?",
    "Let's have a chat. Start whenever you're ready."
]
used_greetings = {}

SPEAKING_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Я всё! Фидбек")],
        [KeyboardButton(text="🏠 Главное меню")]
    ],
    resize_keyboard=True
)

ENCOURAGE_TEXT = "Говори развернуто, так эффективнее для изучения 🗣️"

# ---------- Middleware ----------
async def close_speaking_on_exit(handler, event, data):
    # ... (без изменений, опускаем для краткости, но в реальности он остаётся)
    pass

# ---------- Хендлеры ----------
@router.callback_query(F.data == "start_speaking")
async def start_speaking(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Woman Voice", callback_data="speaking_voice_woman"),
         InlineKeyboardButton(text="👨 Man Voice", callback_data="speaking_voice_man")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text("Выбери голос тьютора:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("speaking_voice_"))
async def select_voice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    voice = callback.data.split("_")[2]
    user_state = get_user_state(user_id)
    user_state["speaking_voice"] = voice
    user_state["mode"] = "speaking_active"
    if "speaking_history" not in user_state:
        user_state["speaking_history"] = []
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)
    await callback.message.delete()

    await callback.message.answer(ENCOURAGE_TEXT, reply_markup=SPEAKING_KEYBOARD)

    if user_id not in used_greetings:
        used_greetings[user_id] = []
    available = [g for g in GREETINGS if g not in used_greetings[user_id]]
    if not available:
        used_greetings[user_id] = []
        available = GREETINGS
    first_message = random.choice(available)
    used_greetings[user_id].append(first_message)

    voice_id = WOMAN_VOICE_ID if voice == "woman" else MAN_VOICE_ID
    try:
        voice_path = await text_to_voice(first_message, voice_id=voice_id)
        if voice_path and os.path.exists(voice_path):
            ogg_path = convert_to_opus(voice_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            # Отправляем без кнопки, затем редактируем
            sent = await callback.message.answer_voice(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=None
            )
            msg_id = sent.message_id
            if user_id not in bot_texts:
                bot_texts[user_id] = {}
            bot_texts[user_id][msg_id] = {"text": first_message, "translation": None}
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}_{msg_id}")]
            ])
            await callback.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=msg_id,
                caption="",
                reply_markup=keyboard
            )
            os.unlink(voice_path)
            os.unlink(ogg_path)
        else:
            await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)

@router.message(F.text == "📊 Я всё! Фидбек")
async def show_feedback(message: Message, state: FSMContext):
    # ... (без изменений, использует show_main_menu с edit=True)

@router.callback_query(F.data == "show_feedback_confirm")
async def confirm_feedback(callback: CallbackQuery, state: FSMContext):
    # ... (без изменений)

@router.message(F.text == "🏠 Главное меню")
async def exit_speaking(message: Message, state: FSMContext):
    # ... (без изменений)

@router.message(SpeakingStates.waiting_for_voice, F.text, ~F.text.startswith('/'))
async def handle_speaking_text(message: Message, state: FSMContext):
    await message.answer("Запишите и отправьте голосовое сообщение.")

@router.message(SpeakingStates.waiting_for_voice, F.photo | F.video | F.video_note | F.animation | F.document | F.sticker)
async def handle_media_in_speaking(message: Message, state: FSMContext):
    await message.answer("Запишите и отправьте голосовое сообщение.")

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    await show_main_menu(callback.message, edit=True)

@router.callback_query(F.data == "continue_speaking")
async def continue_speaking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = "speaking_active"
    set_user_state(user_id, user_state)
    await callback.message.delete()
    await callback.message.answer("Продолжай общение 🗣️", reply_markup=SPEAKING_KEYBOARD)
    await state.set_state(SpeakingStates.waiting_for_voice)

# ---------- НОВЫЕ ХЕНДЛЕРЫ С ПОДДЕРЖКОЙ message_id ----------
@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"translate_text_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=text,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в show_text: {e}")
        await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("translate_text_"))
async def translate_text(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        translation = chat(f"Переведи на русский: {text}", max_tokens=600, temperature=0.3)
        user_texts[msg_id]["translation"] = translation
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="US", callback_data=f"show_original_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=translation,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в translate_text: {e}")
        await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("show_original_"))
async def show_original(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"translate_text_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=text,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в show_original: {e}")
        await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("hide_text_"))
async def hide_text(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption="",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в hide_text: {e}")
        await callback.message.delete()
        await callback.answer("Скрыто.")