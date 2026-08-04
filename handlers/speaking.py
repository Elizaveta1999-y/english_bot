import logging
import os
import random
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import set_user_state, get_user_state
from services.deepseek import chat
from speaking.services.ai import process_voice_message, is_safe_message
from speaking.services.tts import text_to_voice
from states.speaking_states import SpeakingStates
from handlers.voice import convert_to_opus, last_bot_response

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
    "Hello! I'm your English tutor.",
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

# Эту функцию мы будем использовать как глобальный middleware
async def close_speaking_on_exit(handler, event, data):
    user_id = None
    if hasattr(event, 'from_user'):
        user_id = event.from_user.id
    elif hasattr(event, 'message') and event.message:
        user_id = event.message.from_user.id
    elif hasattr(event, 'callback_query') and event.callback_query:
        user_id = event.callback_query.from_user.id

    if not user_id:
        return await handler(event, data)

    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        return await handler(event, data)

    is_speaking_related = False
    if hasattr(event, 'text') and isinstance(event.text, str) and event.text.startswith('/'):
        is_speaking_related = False
    elif hasattr(event, 'data') and isinstance(event.data, str):
        if event.data.startswith("speaking_") or event.data in ("continue_speaking", "back_to_main"):
            is_speaking_related = True
        else:
            is_speaking_related = False
    elif hasattr(event, 'text') and isinstance(event.text, str):
        if event.text in ("📊 Я всё! Фидбек", "🏠 Главное меню"):
            is_speaking_related = True
        else:
            is_speaking_related = False
    else:
        is_speaking_related = False

    if not is_speaking_related:
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        if 'state' in data:
            await data['state'].clear()

        if hasattr(event, 'answer') and callable(event.answer):
            await event.answer()
            await event.message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
        elif hasattr(event, 'reply') and callable(event.reply):
            await event.reply("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
        else:
            await event.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
        return await handler(event, data)

    return await handler(event, data)

@router.callback_query(F.data == "start_speaking")
async def start_speaking(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Woman Voice", callback_data="speaking_voice_woman"),
         InlineKeyboardButton(text="👨 Man Voice", callback_data="speaking_voice_man")]
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
    if "history" not in user_state:
        user_state["history"] = []
    set_user_state(user_id, user_state)

    await state.set_state(SpeakingStates.waiting_for_voice)

    await callback.message.delete()
    
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
            
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
            ])
            sent = await callback.message.answer_voice(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=inline_kb
            )
            last_bot_response[user_id] = {
                "text": first_message,
                "translation": None,
                "audio_message_id": sent.message_id
            }
            user_state["history"].append({"role": "assistant", "text": first_message})
            set_user_state(user_id, user_state)
            
            os.unlink(voice_path)
            os.unlink(ogg_path)
            
            await callback.message.answer(" ", reply_markup=SPEAKING_KEYBOARD)
        else:
            await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)

@router.message(SpeakingStates.waiting_for_voice, F.text)
async def handle_speaking_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        return
    await message.answer("Нажмите на значок микрофона и отправьте голосовое сообщение.")

@router.message(SpeakingStates.waiting_for_voice, F.text == "📊 Я всё! Фидбек")
async def show_feedback(message: Message, state: FSMContext):
    logger.info(f"📊 Фидбек нажат, user={message.from_user.id}")
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("history", [])
    if not history:
        await message.answer("Вы пока ничего не сказали.", reply_markup=ReplyKeyboardRemove())
        return
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
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
        logger.error(f"Ошибка фидбека: {e}")
        await message.answer("Не удалось получить фидбек.", reply_markup=ReplyKeyboardRemove())
        return

    user_state["history"] = []
    set_user_state(user_id, user_state)

    await message.answer("", reply_markup=ReplyKeyboardRemove())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗣️ Продолжить разговор", callback_data="continue_speaking")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await message.answer(f"📊 <b>Фидбек по вашему диалогу:</b>\n\n{feedback}", reply_markup=keyboard, parse_mode="HTML")

@router.message(SpeakingStates.waiting_for_voice, F.text == "🏠 Главное меню")
async def exit_speaking(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        return
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    await message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_feedback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        return
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    await callback.message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

@router.callback_query(F.data == "continue_speaking")
async def continue_speaking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = "speaking_active"
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)

    await callback.message.delete()
    first_message = "Let's continue!"
    voice_id = WOMAN_VOICE_ID if user_state.get("speaking_voice", "woman") == "woman" else MAN_VOICE_ID
    try:
        voice_path = await text_to_voice(first_message, voice_id=voice_id)
        if voice_path and os.path.exists(voice_path):
            ogg_path = convert_to_opus(voice_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
            ])
            sent = await callback.message.answer_voice(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=inline_kb
            )
            last_bot_response[user_id] = {
                "text": first_message,
                "translation": None,
                "audio_message_id": sent.message_id
            }
            user_state["history"].append({"role": "assistant", "text": first_message})
            set_user_state(user_id, user_state)
            os.unlink(voice_path)
            os.unlink(ogg_path)
            await callback.message.answer(" ", reply_markup=SPEAKING_KEYBOARD)
        else:
            await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)