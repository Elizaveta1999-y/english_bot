import logging
import os
import random
import traceback
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ReplyKeyboardRemove, ContentType
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
    logger.info(f"🔹 close_speaking_on_exit вызван для события: {event}")
    user_id = None
    if hasattr(event, 'from_user'):
        user_id = event.from_user.id
    elif hasattr(event, 'message') and event.message:
        user_id = event.message.from_user.id
    elif hasattr(event, 'callback_query') and event.callback_query:
        user_id = event.callback_query.from_user.id

    if not user_id:
        logger.info("🔹 user_id не найден, пропускаем")
        return await handler(event, data)

    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        logger.info(f"🔹 режим не speaking_active (mode={user_state.get('mode')}), пропускаем")
        return await handler(event, data)

    should_close = False
    logger.info(f"🔹 Проверяем событие: {event}")

    if hasattr(event, 'text') and isinstance(event.text, str) and event.text.startswith('/'):
        should_close = True
        logger.info(f"🔹 Команда {event.text} -> закрываем")
    elif hasattr(event, 'data') and isinstance(event.data, str):
        if event.data == "back_to_main":
            should_close = True
            logger.info(f"🔹 callback back_to_main -> закрываем")
        else:
            logger.info(f"🔹 callback {event.data} -> не закрываем")
    elif hasattr(event, 'text') and isinstance(event.text, str):
        if event.text == "🏠 Главное меню":
            should_close = True
            logger.info(f"🔹 Текст '🏠 Главное меню' -> закрываем")
        else:
            logger.info(f"🔹 Текст '{event.text}' -> не закрываем (пропускаем)")
    else:
        logger.info(f"🔹 Событие другого типа -> не закрываем")

    if data.get("skip_exit_message"):
        should_close = False
        logger.info("🔹 skip_exit_message = True, отменяем закрытие")

    if should_close:
        logger.info("🔹 Закрываем диалог")
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

        result = await handler(event, data)
        return result

    logger.info("🔹 Не закрываем диалог, передаём управление хендлеру")
    return await handler(event, data)

@router.callback_query(F.data == "start_speaking")
async def start_speaking(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔵 start_speaking вызван для user {callback.from_user.id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Woman Voice", callback_data="speaking_voice_woman"),
         InlineKeyboardButton(text="👨 Man Voice", callback_data="speaking_voice_man")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    try:
        await callback.message.edit_text("Выбери голос тьютора:", reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}\n{traceback.format_exc()}")
        await callback.message.answer("Выбери голос тьютора:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("speaking_voice_"))
async def select_voice(callback: CallbackQuery, state: FSMContext):
    logger.info(f"🔵 select_voice вызван для user {callback.from_user.id}")
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
            logger.info(f"✅ Сохранён текст в last_bot_response для user {user_id}: {first_message[:30]}...")
            user_state["speaking_history"].append({"role": "assistant", "text": first_message})
            set_user_state(user_id, user_state)
            os.unlink(voice_path)
            os.unlink(ogg_path)
        else:
            logger.warning(f"TTS не сработал для user {user_id}")
            sent = await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
            last_bot_response[user_id] = {
                "text": first_message,
                "translation": None,
                "audio_message_id": sent.message_id,
                "chat_id": callback.message.chat.id,
                "message_id": sent.message_id
            }
    except Exception as e:
        logger.error(f"Ошибка TTS: {e}\n{traceback.format_exc()}")
        sent = await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
        last_bot_response[user_id] = {
            "text": first_message,
            "translation": None,
            "audio_message_id": sent.message_id,
            "chat_id": callback.message.chat.id,
            "message_id": sent.message_id
        }

@router.message(F.text == "📊 Я всё! Фидбек")
async def show_feedback(message: Message, state: FSMContext, data: dict):
    try:
        logger.info(f"📊 show_feedback ВЫЗВАН для user {message.from_user.id}")
        user_id = message.from_user.id
        user_state = get_user_state(user_id)
        history = user_state.get("speaking_history", [])
        logger.info(f"📊 История: {history}")

        user_messages = [msg for msg in history if msg.get('role') == 'user']
        if len(user_messages) < 3:
            data["skip_exit_message"] = True
            await message.answer("Для получения фидбека, запишите несколько голосовых сообщений.")
            return

        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        history_text = "\n".join([f"{msg['role']}: {msg['text']}" for msg in history if msg['role'] in ['user', 'assistant']])
        prompt = (
            "Ты – языковой тренер. Дай краткий фидбек по диалогу пользователя с ИИ в трёх пунктах:\n"
            "1. Грамматика – укажи 2-3 ошибки с исправлениями, если есть.\n"
            "2. Лексика – есть ли повторения, предложи синонимы.\n"
            "3. Общее впечатление – беглость, разнообразие, рекомендации.\n"
            "Не пиши вступлений, приветствий, не используй звёздочки и Markdown. Пиши просто текст.\n"
            f"Диалог:\n{history_text}"
        )
        logger.info(f"📊 Отправляем запрос к DeepSeek: {prompt[:200]}...")
        # chat – синхронная функция, убираем await
        feedback = chat(prompt, max_tokens=300, temperature=0.5)

        user_state["speaking_history"] = []
        set_user_state(user_id, user_state)

        await message.answer("", reply_markup=ReplyKeyboardRemove())
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        await message.answer(f"📊 Фидбек по вашему диалогу:\n\n{feedback}", reply_markup=keyboard, parse_mode="HTML")
        data["skip_exit_message"] = True

    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА В show_feedback: {e}", exc_info=True)
        try:
            await message.answer("Произошла ошибка при получении фидбека. Попробуйте позже.")
        except:
            pass
        data["skip_exit_message"] = True

@router.message(F.text == "🏠 Главное меню")
async def exit_speaking(message: Message, state: FSMContext, data: dict):
    logger.info(f"🏠 Главное меню нажато, user={message.from_user.id}")
    data["skip_exit_message"] = True
    await show_main_menu(message, edit=False)

@router.message(SpeakingStates.waiting_for_voice, F.text)
async def handle_speaking_text(message: Message, state: FSMContext, data: dict):
    data["skip_exit_message"] = True
    await message.answer("Запишите и отправьте голосовое сообщение.")

@router.message(SpeakingStates.waiting_for_voice, F.photo | F.video | F.video_note | F.animation | F.document | F.sticker)
async def handle_media_in_speaking(message: Message, state: FSMContext, data: dict):
    data["skip_exit_message"] = True
    await message.answer("Запишите и отправьте голосовое сообщение.")

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_feedback(callback: CallbackQuery, state: FSMContext, data: dict):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    data["skip_exit_message"] = True
    user_state["mode"] = ""
    set_user_state(user_id, user_state)
    await state.clear()
    await show_main_menu(callback.message, edit=False)

@router.callback_query(F.data == "continue_speaking")
async def continue_speaking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = "speaking_active"
    if "speaking_history" not in user_state:
        user_state["speaking_history"] = []
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)
    await callback.message.delete()

    await callback.message.answer(ENCOURAGE_TEXT, reply_markup=SPEAKING_KEYBOARD)

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
                "audio_message_id": sent.message_id,
                "chat_id": callback.message.chat.id,
                "message_id": sent.message_id
            }
            user_state["speaking_history"].append({"role": "assistant", "text": first_message})
            set_user_state(user_id, user_state)
            os.unlink(voice_path)
            os.unlink(ogg_path)
        else:
            sent = await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
            last_bot_response[user_id] = {
                "text": first_message,
                "translation": None,
                "audio_message_id": sent.message_id,
                "chat_id": callback.message.chat.id,
                "message_id": sent.message_id
            }
    except Exception as e:
        logger.error(f"TTS error: {e}\n{traceback.format_exc()}")
        sent = await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
        last_bot_response[user_id] = {
            "text": first_message,
            "translation": None,
            "audio_message_id": sent.message_id,
            "chat_id": callback.message.chat.id,
            "message_id": sent.message_id
        }

@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery, data: dict):
    try:
        logger.info(f"✅ show_text ВЫЗВАН для user {callback.from_user.id}")
        logger.info(f"   callback.data: {callback.data}")
        logger.info(f"   callback.message: {callback.message}")

        user_id = int(callback.data.split("_")[2])
        logger.info(f"   user_id: {user_id}")

        bot_response = last_bot_response.get(user_id)
        logger.info(f"   last_bot_response для user {user_id}: {bot_response}")

        if not bot_response or not bot_response.get("text"):
            logger.warning(f"❌ Текст НЕ НАЙДЕН для user {user_id}")
            await callback.answer("Нет текста.", show_alert=True)
            return

        text = bot_response["text"]
        logger.info(f"   Текст для user {user_id}: {text[:50]}...")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}")]
        ])

        if callback.message is None:
            logger.error("❌ callback.message is None")
            await callback.answer("Сообщение не найдено.", show_alert=True)
            return

        logger.info(f"   chat_id: {callback.message.chat.id}, message_id: {callback.message.message_id}")

        try:
            await callback.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                caption=text,
                reply_markup=keyboard
            )
            await callback.answer("Текст показан")
            logger.info("✅ Подпись успешно изменена")
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования подписи: {e}\n{traceback.format_exc()}")
            try:
                await callback.message.answer(text, reply_markup=keyboard)
                await callback.answer("Текст показан в отдельном сообщении.")
                logger.info("✅ Текст отправлен отдельным сообщением")
            except Exception as e2:
                logger.error(f"❌ Ошибка отправки отдельного сообщения: {e2}\n{traceback.format_exc()}")
                await callback.answer("Не удалось показать текст.", show_alert=True)

        data["skip_exit_message"] = True
        logger.info("✅ data['skip_exit_message'] = True")

    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА в show_text: {e}\n{traceback.format_exc()}")
        await callback.answer("Произошла ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("translate_text_"))
async def translate_text(callback: CallbackQuery, data: dict):
    try:
        logger.info(f"✅ translate_text вызван для user {callback.from_user.id}")
        user_id = int(callback.data.split("_")[2])
        bot_response = last_bot_response.get(user_id)
        if not bot_response or not bot_response.get("text"):
            await callback.answer("Нет текста для перевода.", show_alert=True)
            return
        text = bot_response["text"]
        # chat – синхронная функция, без await
        translation = chat(f"Переведи на русский: {text}", max_tokens=200, temperature=0.3)
        current_caption = callback.message.caption or ""
        if "Перевод:" in current_caption:
            await callback.answer("Перевод уже показан.", show_alert=True)
            return
        new_caption = current_caption + "\n\n" + translation if current_caption else translation
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}")]
        ])
        try:
            await callback.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                caption=new_caption,
                reply_markup=keyboard
            )
            await callback.answer("Перевод показан")
        except Exception as e:
            logger.error(f"Ошибка редактирования подписи при переводе: {e}\n{traceback.format_exc()}")
            try:
                await callback.message.answer(translation, reply_markup=keyboard)
                await callback.answer("Перевод показан отдельным сообщением.")
            except Exception as e2:
                logger.error(f"Ошибка отправки перевода: {e2}\n{traceback.format_exc()}")
                await callback.answer("Не удалось показать перевод.", show_alert=True)
        data["skip_exit_message"] = True
    except Exception as e:
        logger.error(f"Критическая ошибка в translate_text: {e}\n{traceback.format_exc()}")
        await callback.answer("Произошла ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("hide_text_"))
async def hide_text(callback: CallbackQuery, data: dict):
    try:
        logger.info(f"✅ hide_text вызван для user {callback.from_user.id}")
        user_id = int(callback.data.split("_")[2])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
        ])
        try:
            await callback.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                caption="",
                reply_markup=keyboard
            )
            await callback.answer("Текст скрыт")
        except Exception as e:
            logger.error(f"Ошибка скрытия текста: {e}\n{traceback.format_exc()}")
            try:
                await callback.message.delete()
            except:
                pass
            await callback.answer("Текст скрыт.")
        data["skip_exit_message"] = True
    except Exception as e:
        logger.error(f"Критическая ошибка в hide_text: {e}\n{traceback.format_exc()}")
        await callback.answer("Произошла ошибка.", show_alert=True)