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

# ---------- Middleware (сначала завершение, потом хендлер) ----------
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

    should_close = False

    if hasattr(event, 'text') and isinstance(event.text, str) and event.text.startswith('/'):
        should_close = True
    elif hasattr(event, 'data') and isinstance(event.data, str):
        if event.data == "back_to_main":
            should_close = True
        else:
            should_close = False
    elif hasattr(event, 'text') and isinstance(event.text, str):
        if event.text == "🏠 Главное меню":
            should_close = True
        else:
            should_close = False
    else:
        should_close = False

    if data.get("skip_exit_message"):
        should_close = False

    # Сначала завершаем режим, если нужно
    if should_close:
        try:
            if hasattr(event, 'message') and event.message:
                await event.message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
            elif hasattr(event, 'callback_query') and event.callback_query and event.callback_query.message:
                await event.callback_query.message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
            else:
                await event.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            logger.error(f"Ошибка при удалении клавиатуры: {e}")

        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        if 'state' in data:
            await data['state'].clear()

    # Затем вызываем хендлер
    result = await handler(event, data)
    return result

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
                "audio_message_id": sent.message_id,
                "chat_id": callback.message.chat.id,
                "message_id": sent.message_id
            }
            user_state["speaking_history"].append({"role": "assistant", "text": first_message})
            set_user_state(user_id, user_state)
            os.unlink(voice_path)
            os.unlink(ogg_path)
        else:
            await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)

@router.message(F.text == "📊 Я всё! Фидбек")
async def show_feedback(message: Message, state: FSMContext):
    try:
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
            "4. Похвала – максимум одна короткая фраза за весь ответ, только если действительно есть за что.\n"
            "5. НЕ предлагай практику, упражнения, дополнительные разборы. Просто дай фидбек по тому, что есть.\n"
            "6. Формат: четыре пункта с жирными заголовками через HTML-теги <b>...</b>:\n"
            "   <b>Грамматика</b>\n"
            "   <b>Лексика</b>\n"
            "   <b>Общее впечатление</b> (коротко, 1–2 предложения)\n"
            "   <b>Рекомендации</b> (коротко, 1 предложение – конкретный совет, что улучшить)\n"
            "7. Между пунктами ставь пустую строку. Используй только HTML, без звёздочек и Markdown.\n"
            "8. Общее впечатление должно быть самостоятельным – не повторять ошибки, уже указанные в Грамматике и Лексике. Дай общую оценку беглости, разнообразию, уровню.\n"
            "9. Рекомендации – чёткий практический совет, что именно стоит улучшить (без общих фраз).\n"
            "10. Не пиши в Общем впечатлении фразы типа 'грамматических ошибок нет' – это уже ясно из предыдущих пунктов.\n\n"
            f"Сообщения пользователя:\n{user_texts}\n\n"
            "Твой фидбек (строго по правилам):"
        )

        feedback = chat(prompt, max_tokens=1000, temperature=0.4)

        user_state["pending_feedback"] = feedback
        set_user_state(user_id, user_state)

        if count < 6:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Показать фидбек", callback_data="show_feedback_confirm"),
                    InlineKeyboardButton(text="🗣️ Продолжить", callback_data="continue_speaking")
                ]
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
            await message.answer(
                f"📊 Фидбек по вашему диалогу:\n\n{feedback}",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await message.answer("Диалог завершен. Нажмите «Главное меню», чтобы начать заново.", reply_markup=ReplyKeyboardRemove())
            user_state["mode"] = ""
            set_user_state(user_id, user_state)
    except Exception as e:
        logger.error(f"Ошибка в show_feedback: {e}", exc_info=True)
        await message.answer("Произошла ошибка при получении фидбека. Попробуйте позже.")

@router.callback_query(F.data == "show_feedback_confirm")
async def confirm_feedback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    feedback = user_state.get("pending_feedback")
    if not feedback:
        await callback.message.edit_text("Фидбек не найден. Попробуйте запросить заново.")
        return
    user_state["speaking_history"] = []
    user_state["pending_feedback"] = None
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"📊 Фидбек по вашему диалогу:\n\n{feedback}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.message.answer("Диалог завершен. Нажмите «Главное меню», чтобы начать заново.", reply_markup=ReplyKeyboardRemove())

@router.message(F.text == "🏠 Главное меню")
async def exit_speaking(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    # Отправляем новое сообщение с главным меню, так как это отдельное сообщение
    await show_main_menu(message, edit=False)

@router.message(SpeakingStates.waiting_for_voice, F.text, ~F.text.startswith('/'))
async def handle_speaking_text(message: Message, state: FSMContext):
    await message.answer("Запишите и отправьте голосовое сообщение.")

@router.message(SpeakingStates.waiting_for_voice, F.photo | F.video | F.video_note | F.animation | F.document | F.sticker)
async def handle_media_in_speaking(message: Message, state: FSMContext):
    await message.answer("Запишите и отправьте голосовое сообщение.")

# ---------- ИСПРАВЛЕННЫЕ ХЕНДЛЕРЫ "НАЗАД" и "ГЛАВНОЕ МЕНЮ" ----------
@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    # Редактируем текущее сообщение, показываем главное меню
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")],
        [InlineKeyboardButton(text="📚 Уроки", callback_data="lessons_menu")],
        [InlineKeyboardButton(text="🗣️ Говорение", callback_data="govorenie_menu")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu")]
    ])
    await callback.message.edit_text(
        "👋 Добро пожаловать в English Bot!\nВыберите режим:",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "back_to_main_from_feedback")  # если используется
async def back_to_main_from_feedback(callback: CallbackQuery, state: FSMContext):
    # Аналогично, редактируем сообщение с фидбеком
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")],
        [InlineKeyboardButton(text="📚 Уроки", callback_data="lessons_menu")],
        [InlineKeyboardButton(text="🗣️ Говорение", callback_data="govorenie_menu")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu")]
    ])
    await callback.message.edit_text(
        "👋 Добро пожаловать в English Bot!\nВыберите режим:",
        reply_markup=keyboard
    )

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

# ---------- Кнопка "Текст" и цепочка RUS/US/Скрыть ----------
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