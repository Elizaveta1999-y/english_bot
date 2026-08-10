import os
import tempfile
import subprocess
import logging
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReactionTypeEmoji
from aiogram.fsm.context import FSMContext
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message  # убрали process_roleplay_message
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
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", "-ar", "16000", "-ac", "1", "-b:a", "16k", ogg_path, "-y"]
    subprocess.run(cmd, check=True, capture_output=True)
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
    user_id = message.from_user.id
    chat_id = message.chat.id
    bot = message.bot

    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    current_state = await state.get_state()

    # Игнорируем голосовые в режиме говорения
    if current_state == GovorenieStates.waiting_voice.state:
        return

    is_lesson_active = (
        user_state.get("practice_lesson_key") or
        user_state.get("lesson_qa", {}).get("active") or
        (user_state.get("lesson_mode") == "thematic" and user_state.get("lesson_step") == "awaiting_answer")
    )

    # Если не Speaking и не урок – игнорируем
    if mode != "speaking_active" and not is_lesson_active:
        if mode == "" and user_state.get("pending_feedback"):
            await message.answer("Вы уже получили фидбек. Начните новый диалог, нажав 'Speaking' в главном меню.")
        return

    # ---------- SPEAKING ----------
    if mode == "speaking_active":
        logger.info(f"Speaking voice from user {user_id}")
        if current_state != SpeakingStates.waiting_for_voice:
            await state.set_state(SpeakingStates.waiting_for_voice)

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")

        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        duration = message.voice.duration

        user_text = await voice_to_text(file_bytes.read())
        if not user_text:
            await message.answer("Не понял, повторите.")
            return

        warning = ""
        if duration > 180:
            warning = "Ваше голосовое сообщение длиннее 3 минут, обработана только первая часть. Пожалуйста, записывайте более короткие сообщения для лучшей обработки.\n\n"

        words = user_text.split()
        if len(words) > 500:
            user_text = ' '.join(words[:500])
            warning += "Сообщение слишком длинное, обрезано до 500 слов.\n\n"

        speaking_history = user_state.get("speaking_history", [])
        reply_text, correction_text, is_perfect = await process_voice_message(user_id, user_text, speaking_history)

        # Обновляем user_state после process_voice_message (счётчик напоминания)
        user_state = get_user_state(user_id)

        if reply_text.startswith("Извините, я не могу обсуждать эту тему"):
            await message.answer(reply_text)
            await state.set_state(SpeakingStates.waiting_for_voice)
            return

        # Сохраняем историю
        speaking_history = user_state.get("speaking_history", [])
        speaking_history.append({"role": "user", "text": user_text})
        speaking_history.append({"role": "assistant", "text": reply_text})
        if len(speaking_history) > 20:
            speaking_history = speaking_history[-20:]
        user_state["speaking_history"] = speaking_history
        set_user_state(user_id, user_state)

        if is_perfect:
            try:
                await message.react([ReactionTypeEmoji(emoji="❤️")])
            except Exception as e:
                logger.warning(f"Не удалось поставить реакцию: {e}")

        if warning:
            await message.answer(warning.strip())

        if correction_text:
            await message.answer(correction_text, parse_mode="HTML")

        # TTS
        tts_text = truncate_for_tts(reply_text)
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        voice_pref = user_state.get("speaking_voice", "woman")
        voice_id = WOMAN_VOICE_ID if voice_pref == "woman" else MAN_VOICE_ID

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
                bot_texts[user_id][msg_id] = {"text": reply_text, "translation": None}
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
                await state.set_state(SpeakingStates.waiting_for_voice)
                return
            except Exception as e:
                logger.error(f"Ошибка при отправке голосового: {e}")
        # fallback
        await message.answer(reply_text)
        await state.set_state(SpeakingStates.waiting_for_voice)
        return

    # ---------- УРОКИ ----------
    if is_lesson_active:
        logger.info(f"Lesson voice from user {user_id}")
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

        logger.warning(f"Неизвестный тип урока для user {user_id}")
        return

    logger.info(f"Голосовое от {user_id} не обработано (неизвестный режим)")