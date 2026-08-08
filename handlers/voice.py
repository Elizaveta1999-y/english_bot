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
last_bot_response = {}
last_text_response = {}

WOMAN_VOICE_ID = "8quEMRkSpwEaWBzHvTLv"
MAN_VOICE_ID = "3TStB8f3X3To0Uj5R7RK"

def convert_to_opus(mp3_path: str) -> str:
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", "-ar", "16000", "-ac", "1", "-b:a", "16k", ogg_path, "-y"]
    subprocess.run(cmd, check=True, capture_output=True)
    return ogg_path

async def process_voice_only(user_id: int, user_text: str, history: list = None) -> str:
    reply, _, _ = await process_voice_message(user_id, user_text, history)
    return reply

@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    bot = message.bot

    current_state = await state.get_state()
    user_state = get_user_state(user_id)

    # 1. Если это режим «Говорение» – игнорируем (там свой обработчик)
    if current_state == GovorenieStates.waiting_voice.state:
        logger.info(f"Голосовое от {user_id} пропущено (режим говорение)")
        return

    # 2. Если пользователь НЕ в режиме Speaking, Roleplay или активном уроке – игнорируем
    mode = user_state.get("mode")
    is_lesson_active = (
        user_state.get("practice_lesson_key") or
        user_state.get("lesson_qa", {}).get("active") or
        (user_state.get("lesson_mode") == "thematic" and user_state.get("lesson_step") == "awaiting_answer")
    )

    if mode not in ("speaking_active", "roleplay_active") and not is_lesson_active:
        logger.info(f"Голосовое от {user_id} игнорируется (не в активном режиме, mode={mode})")
        # Не отправляем action, не отвечаем
        return

    # ========== БЛОК SPEAKING ==========
    if current_state == SpeakingStates.waiting_for_voice:
        # Только здесь отправляем индикатор, т.к. будем обрабатывать
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")

        if user_state.get("mode") != "speaking_active":
            user_state["mode"] = "speaking_active"
            set_user_state(user_id, user_state)

        file = await bot.get_file(message.voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        user_text = await voice_to_text(file_bytes.read())
        if not user_text:
            await message.answer("Не понял, повторите.")
            return

        words = user_text.split()
        if len(words) > 500:
            user_text = ' '.join(words[:500])

        speaking_history = user_state.get("speaking_history", [])
        reply_text, correction_text, is_perfect = await process_voice_message(user_id, user_text, speaking_history)

        if reply_text.startswith("Извините, я не могу обсуждать эту тему"):
            await message.answer(reply_text)
            await state.set_state(SpeakingStates.waiting_for_voice)
            return

        last_bot_response[user_id] = {
            "text": reply_text,
            "translation": None,
            "audio_message_id": None,
            "chat_id": chat_id,
            "message_id": None
        }
        logger.info(f"Сохранён текст для user {user_id}: {reply_text[:50]}...")

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
                sent = await message.answer_voice(
                    BufferedInputFile(audio_bytes, filename="voice.ogg"),
                    caption="",
                    reply_markup=keyboard
                )
                if user_id in last_bot_response:
                    last_bot_response[user_id]["audio_message_id"] = sent.message_id
                    last_bot_response[user_id]["message_id"] = sent.message_id
                os.unlink(voice_path)
                os.unlink(ogg_path)
                await state.set_state(SpeakingStates.waiting_for_voice)
                return
            except Exception as e:
                logger.error(f"Audio error: {e}")
        sent = await message.answer(reply_text)
        if user_id in last_bot_response:
            last_bot_response[user_id]["audio_message_id"] = sent.message_id
            last_bot_response[user_id]["message_id"] = sent.message_id
        await state.set_state(SpeakingStates.waiting_for_voice)
        return

    # ========== ОСТАЛЬНЫЕ РЕЖИМЫ (уроки, ролевая игра) ==========
    # Здесь тоже отправляем индикатор, т.к. будем обрабатывать
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

    # Уроки с практикой
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

    # Вопросы в уроках
    if user_state.get("lesson_qa", {}).get("active"):
        from handlers.lessons import process_lesson_question
        await process_lesson_question(user_id, user_text, message.bot, message.chat.id)
        return

    # Тематические уроки
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

    # Ролевая игра
    if mode == "roleplay_active":
        roleplay_history = user_state.get("roleplay_history", [])
        try:
            ai_response = await process_roleplay_message(user_id, user_text, roleplay_history)
        except Exception as e:
            logger.error(f"Ошибка в ролевой игре: {e}")
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
        voice_path = await text_to_voice(ai_response, voice_id=voice_id)
        if voice_path and os.path.exists(voice_path):
            try:
                ogg_path = convert_to_opus(voice_path)
                with open(ogg_path, 'rb') as f:
                    audio_bytes = f.read()
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}")]
                ])
                await message.answer_voice(
                    BufferedInputFile(audio_bytes, filename="voice.ogg"),
                    caption="",
                    reply_markup=keyboard
                )
                os.unlink(voice_path)
                os.unlink(ogg_path)
                return
            except Exception as e:
                logger.error(f"Audio error: {e}")
        await message.answer(ai_response)
        return

    # Если ничего не подошло – игнорируем (но мы уже отсекли выше, оставляем на всякий случай)
    logger.info(f"Голосовое от {user_id} не обработано (неизвестный режим)")