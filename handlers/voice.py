import os
import tempfile
import subprocess
import logging
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReactionTypeEmoji
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
bot_texts = {}

WOMAN_VOICE_ID = "8quEMRkSpwEaWBzHvTLv"
MAN_VOICE_ID = "3TStB8f3X3To0Uj5R7RK"

MAX_TTS_LENGTH = 3000

def convert_to_opus(mp3_path: str) -> str:
    logger.info(f"🔄 convert_to_opus: конвертация {mp3_path} в opus")
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", "-ar", "16000", "-ac", "1", "-b:a", "16k", ogg_path, "-y"]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.info(f"✅ convert_to_opus: готово {ogg_path}")
    return ogg_path

def truncate_for_tts(text: str, max_len: int = MAX_TTS_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + '...'
    return truncated + '...'

async def process_voice_only(user_id: int, user_text: str, history: list = None) -> str:
    reply, _, _ = await process_voice_message(user_id, user_text, history)
    return reply

@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext):
    logger.info("=" * 60)
    logger.info("🔊🔊🔊 handle_voice: НАЧАЛО ОБРАБОТКИ ГОЛОСОВОГО")
    logger.info(f"🔊 user_id: {message.from_user.id}")
    logger.info(f"🔊 message_id: {message.message_id}")
    logger.info(f"🔊 voice.duration: {message.voice.duration} сек")
    logger.info(f"🔊 voice.file_id: {message.voice.file_id}")
    logger.info("=" * 60)

    user_id = message.from_user.id
    chat_id = message.chat.id
    bot = message.bot

    logger.info(f"🔍 ШАГ 1: Получаем состояние пользователя")
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    logger.info(f"🔍 mode = {mode}")
    logger.info(f"🔍 user_state keys: {list(user_state.keys())}")

    logger.info(f"🔍 ШАГ 2: Получаем FSM состояние")
    current_state = await state.get_state()
    logger.info(f"🔍 current_state = {current_state}")

    logger.info(f"🔍 ШАГ 3: Проверка режима говорения")
    if current_state == GovorenieStates.waiting_voice.state:
        logger.info(f"⛔ Голосовое от {user_id} пропущено (режим говорение)")
        return
    logger.info(f"✅ Не говорение, продолжаем")

    logger.info(f"🔍 ШАГ 4: Проверка активности урока")
    is_lesson_active = (
        user_state.get("practice_lesson_key") or
        user_state.get("lesson_qa", {}).get("active") or
        (user_state.get("lesson_mode") == "thematic" and user_state.get("lesson_step") == "awaiting_answer")
    )
    logger.info(f"🔍 is_lesson_active = {is_lesson_active}")

    logger.info(f"🔍 ШАГ 5: Проверка режима")
    if mode not in ("speaking_active", "roleplay_active") and not is_lesson_active:
        logger.info(f"⛔ Голосовое от {user_id} игнорируется (не в активном режиме, mode={mode})")
        if mode == "" and user_state.get("pending_feedback"):
            await message.answer("Вы уже получили фидбек. Начните новый диалог, нажав 'Speaking' в главном меню.")
        return
    logger.info(f"✅ Режим активен, продолжаем")

    # ---------- БЛОК SPEAKING ----------
    if mode == "speaking_active":
        logger.info("=" * 60)
        logger.info(f"🔊🔊🔊 ОБРАБОТКА SPEAKING для user {user_id}")
        logger.info("=" * 60)

        logger.info(f"🔍 ШАГ 6: Устанавливаем состояние SpeakingStates.waiting_for_voice")
        if current_state != SpeakingStates.waiting_for_voice:
            logger.info(f"⚠️ Состояние было {current_state}, меняем на SpeakingStates.waiting_for_voice")
            await state.set_state(SpeakingStates.waiting_for_voice)
        else:
            logger.info(f"✅ Состояние уже SpeakingStates.waiting_for_voice")

        logger.info(f"🔍 ШАГ 7: Отправляем индикатор записи")
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        logger.info(f"✅ Индикатор отправлен")

        logger.info(f"🔍 ШАГ 8: Скачиваем голосовое")
        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        duration = message.voice.duration
        logger.info(f"✅ Голосовое скачано, размер: {len(file_bytes)} байт")

        logger.info(f"🔍 ШАГ 9: Распознаём речь")
        user_text = await voice_to_text(file_bytes.read())
        logger.info(f"🔍 Распознанный текст: '{user_text}'")
        if not user_text:
            logger.warning(f"⚠️ Распознавание вернуло пустой текст")
            await message.answer("Не понял, повторите.")
            return
        logger.info(f"✅ Распознано: {len(user_text)} символов")

        warning = ""
        if duration > 180:
            warning = "Ваше голосовое сообщение длиннее 3 минут, обработана только первая часть. Пожалуйста, записывайте более короткие сообщения для лучшей обработки.\n\n"
            logger.info(f"⚠️ Длительность {duration} сек > 180")

        words = user_text.split()
        if len(words) > 500:
            user_text = ' '.join(words[:500])
            warning += "Сообщение слишком длинное, обрезано до 500 слов.\n\n"
            logger.info(f"⚠️ Обрезано до 500 слов")

        logger.info(f"🔍 ШАГ 10: Вызываем process_voice_message")
        speaking_history = user_state.get("speaking_history", [])
        logger.info(f"🔍 speaking_history длина: {len(speaking_history)}")
        reply_text, correction_text, is_perfect = await process_voice_message(user_id, user_text, speaking_history)
        logger.info(f"✅ process_voice_message вернул:")
        logger.info(f"   reply_text: '{reply_text[:100]}...'")
        logger.info(f"   correction_text: '{correction_text[:100] if correction_text else 'None'}'")
        logger.info(f"   is_perfect: {is_perfect}")

        logger.info(f"🔍 ШАГ 11: Обновляем user_state после process_voice_message")
        user_state = get_user_state(user_id)
        logger.info(f"✅ user_state обновлён")

        logger.info(f"🔍 ШАГ 12: Проверка на отказ")
        if reply_text.startswith("Извините, я не могу обсуждать эту тему"):
            logger.info(f"⛔ Отказ, отправляем текст")
            await message.answer(reply_text)
            await state.set_state(SpeakingStates.waiting_for_voice)
            return
        logger.info(f"✅ Не отказ")

        logger.info(f"🔍 ШАГ 13: Сохраняем историю")
        speaking_history = user_state.get("speaking_history", [])
        speaking_history.append({"role": "user", "text": user_text})
        speaking_history.append({"role": "assistant", "text": reply_text})
        if len(speaking_history) > 20:
            speaking_history = speaking_history[-20:]
        user_state["speaking_history"] = speaking_history
        set_user_state(user_id, user_state)
        logger.info(f"✅ История сохранена, длина: {len(speaking_history)}")

        logger.info(f"🔍 ШАГ 14: Проверка is_perfect")
        if is_perfect:
            try:
                logger.info(f"❤️ Ставим реакцию ❤️")
                await message.react([ReactionTypeEmoji(emoji="❤️")])
                logger.info(f"✅ Реакция поставлена")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось поставить реакцию: {e}")
        else:
            logger.info(f"⏭️ is_perfect=False, реакция не ставится")

        if warning:
            logger.info(f"⚠️ Отправляем warning: {warning}")
            await message.answer(warning.strip())

        if correction_text:
            logger.info(f"📝 Отправляем correction_text")
            await message.answer(correction_text, parse_mode="HTML")
            logger.info(f"✅ correction_text отправлен")

        logger.info(f"🔍 ШАГ 15: Готовим TTS")
        tts_text = truncate_for_tts(reply_text)
        logger.info(f"🔍 tts_text длина: {len(tts_text)} символов")
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        voice_pref = user_state.get("speaking_voice", "woman")
        voice_id = WOMAN_VOICE_ID if voice_pref == "woman" else MAN_VOICE_ID
        logger.info(f"🔍 voice_pref: {voice_pref}, voice_id: {voice_id}")

        logger.info(f"🔍 ШАГ 16: Генерируем голосовое через TTS")
        voice_path = await text_to_voice(tts_text, voice_id=voice_id)
        logger.info(f"🔍 voice_path: {voice_path}")

        if voice_path and os.path.exists(voice_path):
            logger.info(f"✅ TTS файл создан: {voice_path}")
            try:
                logger.info(f"🔍 ШАГ 17: Конвертируем в opus")
                ogg_path = convert_to_opus(voice_path)
                logger.info(f"✅ Конвертировано в opus: {ogg_path}")

                with open(ogg_path, 'rb') as f:
                    audio_bytes = f.read()
                logger.info(f"🔍 audio_bytes размер: {len(audio_bytes)} байт")

                logger.info(f"🔍 ШАГ 18: Отправляем голосовое")
                sent = await message.answer_voice(
                    BufferedInputFile(audio_bytes, filename="voice.ogg"),
                    caption="",
                    reply_markup=None
                )
                msg_id = sent.message_id
                logger.info(f"✅ Голосовое отправлено, message_id: {msg_id}")

                logger.info(f"🔍 ШАГ 19: Сохраняем текст в bot_texts")
                if user_id not in bot_texts:
                    bot_texts[user_id] = {}
                bot_texts[user_id][msg_id] = {"text": reply_text, "translation": None}
                logger.info(f"✅ Текст сохранён в bot_texts[{user_id}][{msg_id}]")

                logger.info(f"🔍 ШАГ 20: Добавляем кнопку 'Текст'")
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}_{msg_id}")]
                ])
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=msg_id,
                    caption="",
                    reply_markup=keyboard
                )
                logger.info(f"✅ Кнопка 'Текст' добавлена")

                os.unlink(voice_path)
                os.unlink(ogg_path)
                logger.info(f"🧹 Временные файлы удалены")

                await state.set_state(SpeakingStates.waiting_for_voice)
                logger.info(f"✅ Состояние установлено SpeakingStates.waiting_for_voice")
                logger.info("=" * 60)
                logger.info("✅✅✅ ОБРАБОТКА SPEAKING ЗАВЕРШЕНА УСПЕШНО")
                logger.info("=" * 60)
                return

            except Exception as e:
                logger.error(f"❌❌❌ ОШИБКА в блоке отправки голосового: {e}", exc_info=True)

        # fallback
        logger.info(f"⚠️ TTS не удался, отправляем текстовый ответ")
        sent = await message.answer(reply_text)
        logger.info(f"✅ Текстовый ответ отправлен")
        await state.set_state(SpeakingStates.waiting_for_voice)
        logger.info("=" * 60)
        logger.info("✅ ОБРАБОТКА SPEAKING ЗАВЕРШЕНА (текстовый fallback)")
        logger.info("=" * 60)
        return

    # ---------- РОЛЕВАЯ ИГРА ----------
    if mode == "roleplay_active":
        logger.info("=" * 60)
        logger.info(f"🎭 ОБРАБОТКА ROLEPLAY для user {user_id}")
        logger.info("=" * 60)

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")

        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        user_text = await voice_to_text(file_bytes.read())
        if not user_text:
            await message.answer("Не понял, повторите.")
            return

        words = user_text.split()
        if len(words) > 500:
            user_text = ' '.join(words[:500])

        roleplay_history = user_state.get("roleplay_history", [])
        try:
            ai_response = await process_roleplay_message(user_id, user_text, roleplay_history)
        except Exception as e:
            logger.error(f"❌ Ошибка в ролевой игре: {e}")
            await message.answer("Произошла ошибка. Попробуйте ещё раз.")
            return

        roleplay_history.append({"role": "user", "text": user_text})
        roleplay_history.append({"role": "assistant", "text": ai_response})
        if len(roleplay_history) > 20:
            roleplay_history = roleplay_history[-20:]
        user_state["roleplay_history"] = roleplay_history
        set_user_state(user_id, user_state)

        if ai_response.startswith("Извините, я не могу обсуждать эту тему"):
            await message.answer(ai_response)
            return

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        voice_pref = user_state.get("speaking_voice", "woman")
        voice_id = WOMAN_VOICE_ID if voice_pref == "woman" else MAN_VOICE_ID
        tts_text = truncate_for_tts(ai_response)
        voice_path = await text_to_voice(tts_text, voice_id=voice_id)
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
                    [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}_{msg_id}")]
                ])
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=msg_id,
                    caption="",
                    reply_markup=keyboard
                )
                os.unlink(voice_path)
                os.unlink(ogg_path)
                return
            except Exception as e:
                logger.error(f"❌ Audio error в roleplay: {e}")
        await message.answer(ai_response)
        return

    # ---------- УРОКИ ----------
    if is_lesson_active:
        logger.info("=" * 60)
        logger.info(f"📚 ОБРАБОТКА УРОКА для user {user_id}")
        logger.info("=" * 60)

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")

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

        logger.info(f"⚠️ Голосовое от {user_id} в режиме урока не обработано")
        return

    logger.info(f"❌ Голосовое от {user_id} не обработано (неизвестный режим)")
    logger.info("=" * 60)