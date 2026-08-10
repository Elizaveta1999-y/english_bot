import os
import logging
import re
import random
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
from speaking.services.stt import voice_to_text
from speaking.services.tts import text_to_voice
from handlers.voice import convert_to_opus, bot_texts
from services.deepseek import chat
from handlers.roleplay import build_system_prompt, call_ai_with_system, is_forbidden, is_cyrillic, RoleplayStates

logger = logging.getLogger(__name__)
router = Router()

WOMAN_VOICE_ID = "8quEMRkSpwEaWBzHvTLv"
MAN_VOICE_ID = "3TStB8f3X3To0Uj5R7RK"
MAX_TTS_LENGTH = 3000

def truncate_for_tts(text: str, max_len: int = MAX_TTS_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + '...'
    return truncated + '...'

# ============================================================
# Обработчик голосовых сообщений только для ролевой игры
# ============================================================
@router.message(F.voice | F.audio, RoleplayStates.active)
async def roleplay_voice_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    if user_state.get("mode") != "roleplay_active":
        logger.info(f"Голосовое от {user_id} проигнорировано (mode != roleplay_active)")
        return

    logger.info(f"Голосовое в ролевой игре от {user_id}")

    await message.bot.send_chat_action(chat_id=message.chat.id, action="record_voice")

    try:
        audio_obj = message.voice or message.audio
        if audio_obj is None:
            await message.answer("Не удалось найти аудиофайл.")
            return
        file = await message.bot.get_file(audio_obj.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        text = await voice_to_text(file_bytes.read())
    except Exception as e:
        logger.error(f"Ошибка распознавания в roleplay_voice: {e}")
        await message.answer("Не удалось распознать голосовое сообщение. Попробуйте написать текстом.")
        return

    if not text:
        await message.answer("Не удалось распознать речь. Попробуйте сказать чётче или напишите текстом.")
        return

    if is_forbidden(text):
        await message.answer("Пожалуйста, не отходите от темы диалога. Давайте продолжим ролевую игру в рамках заданной ситуации.")
        return

    if is_cyrillic(text):
        counter = user_state.get("russian_counter", 0) + 1
        user_state["russian_counter"] = counter
        set_user_state(user_id, user_state)
        show_english_reminder = (counter % 3 == 0)
    else:
        show_english_reminder = False

    topic = user_state.get("roleplay_topic", "")
    description = user_state.get("roleplay_description", "")
    goals = user_state.get("roleplay_goals", [])
    system_prompt = build_system_prompt(topic, description, goals)
    history = user_state.get("roleplay_history", [])

    ai_response = await call_ai_with_system(system_prompt, text, history, max_tokens=250)

    history.append({"role": "user", "text": text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["roleplay_history"] = history
    set_user_state(user_id, user_state)

    if show_english_reminder:
        await message.answer("Feel free to use English!")

    # Случайный голос
    voice_id = random.choice([WOMAN_VOICE_ID, MAN_VOICE_ID])
    tts_text = truncate_for_tts(ai_response)

    await message.bot.send_chat_action(chat_id=message.chat.id, action="record_voice")

    # Попытка синтеза голоса
    try:
        voice_path = await text_to_voice(tts_text, voice_id=voice_id)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        voice_path = None

    if voice_path and os.path.exists(voice_path):
        try:
            ogg_path = convert_to_opus(voice_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            sent = await message.answer_voice(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=None
            )
            msg_id = sent.message_id
            if user_id not in bot_texts:
                bot_texts[user_id] = {}
            bot_texts[user_id][msg_id] = {"text": ai_response, "translation": None}
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"roleplay_voice_show_text_{user_id}_{msg_id}")]
            ])
            await message.bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=msg_id,
                caption="",
                reply_markup=keyboard
            )
            os.unlink(voice_path)
            os.unlink(ogg_path)
            return
        except Exception as e:
            logger.error(f"Audio error in roleplay_voice: {e}")
            # Если голос не удался – отправляем текст
            await message.answer(ai_response)
            return

    # Если голос не удался, отправляем текстом
    sent_text = await message.answer(ai_response)
    msg_id = sent_text.message_id
    if user_id not in bot_texts:
        bot_texts[user_id] = {}
    bot_texts[user_id][msg_id] = {"text": ai_response, "translation": None}
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перевести", callback_data=f"roleplay_voice_translate_{user_id}_{msg_id}")]
    ])
    await message.bot.edit_message_text(
        ai_response,
        chat_id=message.chat.id,
        message_id=msg_id,
        reply_markup=keyboard
    )

# ============================================================
# ОБРАБОТЧИКИ КНОПОК ДЛЯ ГОЛОСОВЫХ
# ============================================================
@router.callback_query(lambda c: c.data.startswith("roleplay_voice_show_text_"))
async def roleplay_voice_show_text(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[4])
        msg_id = int(parts[5])
        logger.info(f"roleplay_voice_show_text: user_id={user_id}, msg_id={msg_id}")
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"roleplay_voice_translate_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"roleplay_voice_hide_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=text,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в roleplay_voice_show_text: {e}", exc_info=True)
        await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("roleplay_voice_translate_"))
async def roleplay_voice_translate(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[4])
        msg_id = int(parts[5])
        logger.info(f"roleplay_voice_translate: user_id={user_id}, msg_id={msg_id}")
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        if user_texts[msg_id]["translation"]:
            translation = user_texts[msg_id]["translation"]
        else:
            translation = chat(f"Переведи на русский: {text}", max_tokens=600, temperature=0.3)
            user_texts[msg_id]["translation"] = translation
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="US", callback_data=f"roleplay_voice_original_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"roleplay_voice_hide_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=translation,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в roleplay_voice_translate: {e}", exc_info=True)
        await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("roleplay_voice_original_"))
async def roleplay_voice_original(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[4])
        msg_id = int(parts[5])
        logger.info(f"roleplay_voice_original: user_id={user_id}, msg_id={msg_id}")
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"roleplay_voice_translate_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"roleplay_voice_hide_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=text,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в roleplay_voice_original: {e}", exc_info=True)
        await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("roleplay_voice_hide_"))
async def roleplay_voice_hide(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[4])
        msg_id = int(parts[5])
        logger.info(f"roleplay_voice_hide: user_id={user_id}, msg_id={msg_id}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Текст", callback_data=f"roleplay_voice_show_text_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption="🔒",
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в roleplay_voice_hide: {e}", exc_info=True)
        await callback.message.delete()
        await callback.answer("Скрыто.")