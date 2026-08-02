import os
import tempfile
import subprocess
import logging
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReactionTypeEmoji, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message, process_roleplay_message
from speaking.services.tts import text_to_voice
from data.users import get_user_state, set_user_state, set_user_mode
from services.deepseek import chat
from handlers.lessons import show_practice_task, parse_user_answers
from handlers.govorenie import GovorenieStates
from states.speaking_states import SpeakingStates

logger = logging.getLogger(__name__)

router = Router()
last_bot_response = {}
last_text_response = {}

WOMAN_VOICE_ID = "8quEMRkSpwEaWBzHvTLv"
MAN_VOICE_ID = "3TStB8f3X3To0Uj5R7RK"

# Клавиатура для режима Speaking
SPEAKING_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Я всё! Фидбек")],
        [KeyboardButton(text="🏠 Главное меню")]
    ],
    resize_keyboard=True
)

def convert_to_opus(mp3_path: str) -> str:
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", "-ar", "16000", "-ac", "1", "-b:a", "16k", ogg_path, "-y"]
    subprocess.run(cmd, check=True, capture_output=True)
    return ogg_path

async def process_voice_only(user_id: int, user_text: str) -> str:
    from speaking.services.ai import process_voice_message
    reply, _, _ = await process_voice_message(user_id, user_text)
    return reply

@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    bot = message.bot

    await bot.send_chat_action(chat_id=chat_id, action="record_voice")

    current_state = await state.get_state()

    if current_state == GovorenieStates.waiting_voice.state:
        logger.info(f"Голосовое от {user_id} пропущено (говорение)")
        return

    user_state = get_user_state(user_id)

    # ====== РЕЖИМ SPEAKING ======
    if current_state == SpeakingStates.waiting_for_voice:
        if user_state.get("mode") != "speaking_active":
            user_state["mode"] = "speaking_active"
            set_user_state(user_id, user_state)

        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        user_text = await voice_to_text(file_bytes.read())
        if not user_text:
            await message.answer("Не понял, повторите.")
            await message.answer("🎙️", reply_markup=SPEAKING_KEYBOARD)
            return

        words = user_text.split()
        if len(words) > 500:
            user_text = ' '.join(words[:500])

        reply_text, correction_text, is_perfect = await process_voice_message(user_id, user_text)

        history = user_state.get("history", [])
        history.append({"role": "user", "text": user_text})
        history.append({"role": "assistant", "text": reply_text})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)

        if is_perfect:
            try:
                await message.react([ReactionTypeEmoji(emoji="❤️")])
            except Exception as e:
                logger.warning(f"Не удалось поставить реакцию: {e}")

        if correction_text:
            await message.answer(correction_text, parse_mode="HTML")

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        voice_pref = user_state.get("speaking_voice", "woman")
        voice_id = WOMAN_VOICE_ID if voice_pref == "woman" else MAN_VOICE_ID
        voice_path = await text_to_voice(reply_text, voice_id=voice_id)
        if voice_path and os.path.exists(voice_path):
            try:
                ogg_path = convert_to_opus(voice_path)
                with open(ogg_path, 'rb') as f:
                    audio_bytes = f.read()
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
                ])
                sent = await message.answer_audio(
                    BufferedInputFile(audio_bytes, filename="voice.ogg"),
                    caption="",
                    reply_markup=keyboard
                )
                last_bot_response[user_id] = {
                    "text": reply_text,
                    "translation": None,
                    "audio_message_id": sent.message_id
                }
                os.unlink(voice_path)
                os.unlink(ogg_path)
                await message.answer("🎙️", reply_markup=SPEAKING_KEYBOARD)
                return
            except Exception as e:
                logger.error(f"Audio error: {e}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}")]
        ])
        sent = await message.answer(reply_text, reply_markup=keyboard)
        last_text_response[user_id] = {"text": reply_text, "translation": None, "message_id": sent.message_id}
        await message.answer("🎙️", reply_markup=SPEAKING_KEYBOARD)
        return

    # ====== ОСТАЛЬНАЯ ЛОГИКА ======
    file = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())
    if not user_text:
        await message.answer("Не понял, повторите.")
        return

    words = user_text.split()
    if len(words) > 500:
        user_text = ' '.join(words[:500])

    if user_state.get("practice_lesson_key"):
        lesson_key = user_state["practice_lesson_key"]
        practice = user_state.get("practice", {}).get(lesson_key)
        if practice:
            task_idx = practice.get("session_index", 0)
            tasks = practice.get("tasks", [])
            if task_idx >= len(tasks):
                await show_practice_task(message, user_id, edit=False)
                return

            task = tasks[task_idx]
            subtasks = task.get("subtasks", [])
            if not subtasks:
                await message.answer("Ошибка: нет подзаданий")
                return

            user_answers = parse_user_answers(user_text.strip(), len(subtasks))
            while len(user_answers) < len(subtasks):
                user_answers.append("")

            correct_count = 0
            wrong_list = []
            for i, subtask in enumerate(subtasks):
                user_ans = user_answers[i].strip() if i < len(user_answers) else ""
                correct = subtask.get("answer", "").strip()
                if user_ans.lower() == correct.lower():
                    correct_count += 1
                else:
                    wrong_list.append({
                        "question": subtask.get("question", ""),
                        "your": user_ans if user_ans else "(пусто)",
                        "correct": correct
                    })

            practice["session_correct"] += correct_count
            practice["session_index"] += 1
            set_user_state(user_id, user_state)

            if not wrong_list:
                await message.answer(f"✅ Отлично! Все {len(subtasks)} ответов верны!")
            else:
                summary = f"❌ Правильно: {correct_count} из {len(subtasks)}\n\n"
                for w in wrong_list:
                    summary += f"• {w['question']}\n   Ваш ответ: {w['your']} → правильно: {w['correct']}\n\n"
                await message.answer(summary)

            if practice["session_index"] >= len(tasks):
                await show_practice_task(message, user_id, edit=False)
            else:
                await show_practice_task(message, user_id, edit=False)
            return

    if user_state.get("lesson_qa", {}).get("active"):
        from handlers.lessons import process_lesson_question
        await process_lesson_question(user_id, user_text, message.bot, message.chat.id)
        return

    if user_state.get("lesson_mode") == "thematic" and user_state.get("lesson_step") == "awaiting_answer":
        from handlers.lesson_utils import check_answer
        task = user_state.get("lesson_task")
        if task:
            feedback = await check_answer(user_text, task)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать ещё раз", callback_data="retry_lesson")],
                [InlineKeyboardButton(text="📝 Следующее задание", callback_data="next_task")],
                [InlineKeyboardButton(text="❌ Завершить", callback_data="exit_lesson")]
            ])
            await message.answer(f"📊 Результат:\n\n{feedback}", reply_markup=keyboard)
            user_state["lesson_step"] = "feedback_shown"
            set_user_state(user_id, user_state)
            return

    mode = user_state.get("mode")
    if mode == "roleplay_active":
        ai_response = await process_roleplay_message(user_id, user_text)
    else:
        if mode != "speaking_active":
            set_user_mode(user_id, "speaking_active")
        ai_response = await process_voice_only(user_id, user_text)

    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    await bot.send_chat_action(chat_id=chat_id, action="record_voice")
    voice_pref = user_state.get("speaking_voice", "woman")
    voice_id = WOMAN_VOICE_ID if voice_pref == "woman" else MAN_VOICE_ID
    voice_path = await text_to_voice(ai_response, voice_id=voice_id)
    if voice_path and os.path.exists(voice_path):
        try:
            ogg_path = convert_to_opus(voice_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
            ])
            sent = await message.answer_audio(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=keyboard
            )
            last_bot_response[user_id] = {"text": ai_response, "translation": None, "audio_message_id": sent.message_id}
            os.unlink(voice_path)
            os.unlink(ogg_path)
            if user_state.get("mode") == "speaking_active":
                await message.answer("🎙️", reply_markup=SPEAKING_KEYBOARD)
            return
        except Exception as e:
            logger.error(f"Audio error: {e}")
    else:
        logger.warning("TTS returned None, sending text")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    sent = await message.answer(ai_response, reply_markup=keyboard)
    last_text_response[user_id] = {"text": ai_response, "translation": None, "message_id": sent.message_id}
    if user_state.get("mode") == "speaking_active":
        await message.answer("🎙️", reply_markup=SPEAKING_KEYBOARD)

# ---------- ОБРАБОТЧИКИ КНОПОК ----------
@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста.", show_alert=True)
        return
    original = data["text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перевести", callback_data=f"translate_{user_id}"),
         InlineKeyboardButton(text="Скрыть", callback_data=f"hide_{user_id}")]
    ])
    new_caption = f"📝 {original}"
    if callback.message.caption == new_caption:
        await callback.answer("Текст уже показан", show_alert=False)
        return
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=new_caption,
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_") and not c.data.startswith("translate_text_"))
async def translate_caption(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста.", show_alert=True)
        return
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(f"Translate to Russian. Output ONLY translation:\n\n{data['text']}", max_tokens=300, temperature=0.3)
        translation = translation.strip('*"\'')
        data["translation"] = translation
        last_bot_response[user_id] = data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оригинал", callback_data=f"original_{user_id}"),
         InlineKeyboardButton(text="Скрыть", callback_data=f"hide_{user_id}")]
    ])
    new_caption = f"🇷🇺 {translation}"
    if callback.message.caption == new_caption:
        await callback.answer("Уже переведено", show_alert=False)
        return
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=new_caption,
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_") and not c.data.startswith("original_text_"))
async def revert_to_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перевести", callback_data=f"translate_{user_id}"),
         InlineKeyboardButton(text="Скрыть", callback_data=f"hide_{user_id}")]
    ])
    new_caption = f"📝 {data['text']}"
    if callback.message.caption == new_caption:
        await callback.answer("Уже оригинал", show_alert=False)
        return
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=new_caption,
        reply_markup=keyboard
    )
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("hide_") and not c.data.startswith("hide_text_"))
async def hide_message(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("audio_message_id"):
        await callback.answer("Нет сообщения.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
    ])
    if callback.message.caption == "":
        await callback.answer("Уже скрыто", show_alert=False)
        return
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption="",
        reply_markup=keyboard
    )
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("translate_text_"))
async def translate_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста для перевода.", show_alert=True)
        return
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(f"Translate to Russian. Output ONLY translation:\n\n{data['text']}", max_tokens=300, temperature=0.3)
        translation = translation.strip('*"\'')
        data["translation"] = translation
        last_text_response[user_id] = data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оригинал", callback_data=f"original_text_{user_id}")]
    ])
    new_text = f"🇷🇺 {translation}"
    if callback.message.text == new_text:
        await callback.answer("Уже переведено", show_alert=False)
        return
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["message_id"],
        text=new_text,
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("original_text_"))
async def original_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    new_text = data["text"]
    if callback.message.text == new_text:
        await callback.answer("Уже оригинал", show_alert=False)
        return
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["message_id"],
        text=new_text,
        reply_markup=keyboard
    )
    data["translation"] = None
    last_text_response[user_id] = data
    await callback.answer()

# ===== ОБРАБОТЧИКИ ВЫБОРА ГОЛОСА (с первым ответом ИИ) =====
@router.callback_query(F.data == "speaking_voice_woman")
async def set_woman_voice(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["speaking_voice"] = "woman"
    user_state["mode"] = "speaking_active"
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)

    # Удаляем сообщение с выбором голоса
    await callback.message.delete()

    # Первый ответ от ИИ (приветствие)
    first_text = "Hello! Let's practice English. Send me a voice message, and I'll reply."
    # Добавляем в историю
    history = user_state.get("history", [])
    history.append({"role": "assistant", "text": first_text})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    # Отправляем голосовое
    voice_pref = user_state.get("speaking_voice", "woman")
    voice_id = WOMAN_VOICE_ID if voice_pref == "woman" else MAN_VOICE_ID
    voice_path = await text_to_voice(first_text, voice_id=voice_id)
    if voice_path and os.path.exists(voice_path):
        try:
            ogg_path = convert_to_opus(voice_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
            ])
            sent = await callback.message.answer_audio(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=keyboard
            )
            last_bot_response[user_id] = {
                "text": first_text,
                "translation": None,
                "audio_message_id": sent.message_id
            }
            os.unlink(voice_path)
            os.unlink(ogg_path)
        except Exception as e:
            logger.error(f"Audio error: {e}")
            # если не удалось отправить аудио, отправляем текстом
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}")]
            ])
            sent = await callback.message.answer(first_text, reply_markup=keyboard)
            last_text_response[user_id] = {"text": first_text, "translation": None, "message_id": sent.message_id}
    else:
        # TTS не сработал – текст
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}")]
        ])
        sent = await callback.message.answer(first_text, reply_markup=keyboard)
        last_text_response[user_id] = {"text": first_text, "translation": None, "message_id": sent.message_id}

    # Отправляем клавиатуру (без микрофона, просто кнопки)
    await callback.message.answer("Выберите действие:", reply_markup=SPEAKING_KEYBOARD)
    await callback.answer()

@router.callback_query(F.data == "speaking_voice_man")
async def set_man_voice(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["speaking_voice"] = "man"
    user_state["mode"] = "speaking_active"
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)

    await callback.message.delete()

    first_text = "Hello! Let's practice English. Send me a voice message, and I'll reply."
    history = user_state.get("history", [])
    history.append({"role": "assistant", "text": first_text})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    voice_pref = user_state.get("speaking_voice", "woman")
    voice_id = WOMAN_VOICE_ID if voice_pref == "woman" else MAN_VOICE_ID
    voice_path = await text_to_voice(first_text, voice_id=voice_id)
    if voice_path and os.path.exists(voice_path):
        try:
            ogg_path = convert_to_opus(voice_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
            ])
            sent = await callback.message.answer_audio(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=keyboard
            )
            last_bot_response[user_id] = {
                "text": first_text,
                "translation": None,
                "audio_message_id": sent.message_id
            }
            os.unlink(voice_path)
            os.unlink(ogg_path)
        except Exception as e:
            logger.error(f"Audio error: {e}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}")]
            ])
            sent = await callback.message.answer(first_text, reply_markup=keyboard)
            last_text_response[user_id] = {"text": first_text, "translation": None, "message_id": sent.message_id}
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перевести", callback_data=f"translate_text_{user_id}")]
        ])
        sent = await callback.message.answer(first_text, reply_markup=keyboard)
        last_text_response[user_id] = {"text": first_text, "translation": None, "message_id": sent.message_id}

    await callback.message.answer("Выберите действие:", reply_markup=SPEAKING_KEYBOARD)
    await callback.answer()

# ---------- ОБРАБОТЧИКИ КНОПОК КЛАВИАТУРЫ SPEAKING ----------
@router.message(F.text == "📊 Я всё! Фидбек")
async def feedback_button(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.set_state(None)
    user_state = get_user_state(user_id)
    if user_state.get("mode") == "speaking_active":
        user_state["mode"] = "default"
        set_user_state(user_id, user_state)
    await message.answer("📊 Фидбек: вы завершили Speaking-сессию. Ваши ответы сохранены.", reply_markup=ReplyKeyboardRemove())

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.set_state(None)
    user_state = get_user_state(user_id)
    if user_state.get("mode") == "speaking_active":
        user_state["mode"] = "default"
        set_user_state(user_id, user_state)
    await message.answer("🏠 Главное меню", reply_markup=ReplyKeyboardRemove())
