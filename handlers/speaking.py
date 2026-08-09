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
from handlers.voice import convert_to_opus, last_bot_response
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

async def close_speaking_on_exit(handler, event, data):
    # ... (без изменений) ...
    pass

@router.callback_query(F.data == "start_speaking")
async def start_speaking(callback: CallbackQuery, state: FSMContext):
    # ... (без изменений) ...
    pass

@router.callback_query(F.data.startswith("speaking_voice_"))
async def select_voice(callback: CallbackQuery, state: FSMContext):
    # ... (без изменений) ...
    pass

@router.message(F.text == "📊 Я всё! Фидбек")
async def show_feedback(message: Message, state: FSMContext):
    try:
        logger.info(f"📊 Фидбек нажат, user={message.from_user.id}")
        user_id = message.from_user.id
        user_state = get_user_state(user_id)
        history = user_state.get("speaking_history", [])
        user_messages = [msg for msg in history if msg.get('role') == 'user']
        count = len(user_messages)

        if count < 3:
            await message.answer("Запишите несколько голосовых сообщений, чтобы получить фидбек.")
            return

        has_english = False
        for msg in user_messages:
            if re.search(r'[a-zA-Z]', msg.get('text', '')):
                has_english = True
                break

        if not has_english:
            await message.answer(
                "🗣️ Вы не использовали английский в этом диалоге.\n\n"
                "Старайтесь отвечать по-английски – это поможет вам быстрее прогрессировать.\n"
                "Попробуйте ещё раз!"
            )
            return

        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

        user_texts = "\n".join([f"Пользователь: {msg['text']}" for msg in user_messages])

        prompt = (
            "Ты – опытный преподаватель английского языка. Проанализируй речь пользователя в этом диалоге.\n\n"
            "ЖЁСТКИЕ ПРАВИЛА (не нарушать!):\n"
            "1. Анализируй ТОЛЬКО сообщения пользователя на английском. Игнорируй русский язык полностью.\n"
            "2. НЕ используй приветствия, обращения (ученик, пользователь, ты и т.п.). Начинай сразу с сути.\n"
            "3. НЕ оценивай пунктуацию и заглавные буквы – только грамматику (времена, порядок слов, предлоги, артикли) и лексику (повторы, синонимы).\n"
            "4. Похвала – максимум одна короткая фраза за весь ответ, только если действительно есть что похвалить.\n"
            "5. НЕ предлагай практику, упражнения, дополнительные разборы. Просто дай фидбек по тому, что есть.\n"
            "6. Формат: три пункта с жирными заголовками через HTML-теги <b>...</b>:\n"
            "   <b>Грамматика</b>\n"
            "   <b>Лексика</b>\n"
            "   <b>Общее впечатление</b> (коротко, 1–2 предложения)\n"
            "7. Между пунктами ставь пустую строку. Используй только HTML, без звёздочек и Markdown.\n"
            "8. Общее впечатление должно быть сдержанным, без излишней эмоциональности.\n\n"
            f"Сообщения пользователя:\n{user_texts}\n\n"
            "Твой фидбек (строго по правилам):"
        )

        feedback = chat(prompt, max_tokens=1000, temperature=0.4)

        user_state["pending_feedback"] = feedback
        set_user_state(user_id, user_state)

        if count < 6:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Показать фидбек", callback_data="show_feedback_confirm"),
                 InlineKeyboardButton(text="🗣️ Продолжить", callback_data="continue_speaking")]
            ])
            await message.answer(
                "У вас пока мало сообщений, фидбек может быть неполным.",
                reply_markup=keyboard
            )
        else:
            user_state["speaking_history"] = []
            user_state["pending_feedback"] = None
            set_user_state(user_id, user_state)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
            ])
            await message.answer(f"📊 Фидбек по вашему диалогу:\n\n{feedback}", reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка в show_feedback: {e}", exc_info=True)
        await message.answer("Произошла ошибка при получении фидбека. Попробуйте позже.")

# Остальные хендлеры (показ текста, перевод, скрытие) – исправляем кнопки

@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[2])
        bot_response = last_bot_response.get(user_id)
        if not bot_response or not bot_response.get("text"):
            await callback.answer("Нет текста.", show_alert=True)
            return
        text = bot_response["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"translate_text_{user_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}")]
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
        user_id = int(callback.data.split("_")[2])
        bot_response = last_bot_response.get(user_id)
        if not bot_response or not bot_response.get("text"):
            await callback.answer("Нет текста.", show_alert=True)
            return
        text = bot_response["text"]
        translation = chat(f"Переведи на русский: {text}", max_tokens=200, temperature=0.3)
        # Показываем перевод, кнопки US и Скрыть
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="US", callback_data=f"show_original_{user_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}")]
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
        user_id = int(callback.data.split("_")[2])
        bot_response = last_bot_response.get(user_id)
        if not bot_response or not bot_response.get("text"):
            await callback.answer("Нет текста.", show_alert=True)
            return
        text = bot_response["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"translate_text_{user_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}")]
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
        user_id = int(callback.data.split("_")[2])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
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