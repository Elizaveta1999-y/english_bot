import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
from speaking.services.stt import voice_to_text
from services.deepseek import chat
import re

logger = logging.getLogger(__name__)
router = Router()

# ============================================================
# Этот обработчик будет перехватывать голосовые сообщения
# только в режиме ролевой игры.
# Для регистрации: помести его РАНЬШЕ основного voice.router
# в app.py или handlers/__init__.py
# ============================================================

@router.message(F.voice | F.audio)
async def roleplay_voice_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    # Если не в ролевой игре – просто выходим, ничего не делаем
    if user_state.get("mode") != "roleplay_active":
        return

    logger.info(f"Голосовое в ролевой игре от {user_id}")

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

    # Проверка на запрещённые слова (если нужно)
    forbidden = ["fuck", "bitch", "shit", "cunt", "dick", "pussy", "fucking", "motherfucker", "asshole", "bastard", "damn",
                 "penis", "vagina", "cum", "orgasm", "masturbate", "sperm", "erection", "prostitute", "porn", "xxx",
                 "suicide", "kill myself", "cut myself", "self-harm", "die", "death", "hang myself", "overdose",
                 "murder", "rape", "torture", "assault", "kill", "terrorist", "bomb", "shoot", "stab",
                 "nazi", "hitler", "stalin", "terrorism", "dictator", "fascist", "communist", "putin", "zelensky", "trump", "biden",
                 "allah", "muhammad", "jesus", "bible", "quran", "prophet", "church", "mosque", "synagogue", "god", "holy", "priest", "imam"]
    lower = text.lower()
    for word in forbidden:
        if word in lower:
            await message.answer("Пожалуйста, не отходите от темы диалога. Давайте продолжим ролевую игру в рамках заданной ситуации.")
            return

    # Проверка на кириллицу для напоминания про английский
    if re.search('[а-яА-Я]', text):
        counter = user_state.get("russian_counter", 0) + 1
        user_state["russian_counter"] = counter
        set_user_state(user_id, user_state)
        show_english_reminder = (counter % 5 == 0)
    else:
        show_english_reminder = False

    topic = user_state.get("roleplay_topic", "")
    description = user_state.get("roleplay_description", "")
    goals = user_state.get("roleplay_goals", [])

    goals_text = "\n".join([f"{i+1}. {g}" for i, g in enumerate(goals)])
    system_prompt = (
        f"You are a character in a role-playing game for learning English. "
        f"Situation: {description}\n"
        f"Topic: {topic}\n"
        f"User's goals: {goals_text}\n\n"
        "Your task is to lead the dialogue within this situation. "
        "You must help the user practice English, but stay in character.\n\n"
        "IMPORTANT RULES:\n"
        "1. You ALWAYS respond in ENGLISH only. Never switch to Russian, regardless of the user's language.\n"
        "2. If the user goes off-topic, gently remind them of the situation. However, allow creative freedom – "
        "if the user is describing their product, presenting an idea, or developing the situation within the scenario, "
        "it is NOT considered off-topic. Only warn if the user starts talking about completely unrelated things "
        "(e.g., their personal life, politics, other topics not related to the role).\n"
        "3. You do not discuss topics unrelated to the role-play. Do not answer questions about yourself, "
        "the real world, politics, religion, sex, violence, or suicide.\n"
        "4. If the user asks about something forbidden, respond with: 'Let's return to our situation' and continue the game.\n"
        "5. At the end of each of your responses, assess whether the user has achieved all goals. "
        "If all goals are achieved and the dialogue has more than 5 exchanges, add this phrase: "
        "'It seems we've reached a logical conclusion to this situation. If you'd like, we can wrap up and get feedback. "
        "If you prefer to continue, just keep chatting.'\n"
        "6. Respond naturally, in character. Continue the dialogue based on the user's messages.\n"
    )

    history = user_state.get("roleplay_history", [])

    # Формируем промпт
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["text"]})
    messages.append({"role": "user", "content": text})
    prompt = ""
    for m in messages:
        prompt += f"{m['role']}: {m['content']}\n"

    try:
        response = chat(prompt, max_tokens=500, temperature=0.7)
    except Exception as e:
        logger.error(f"Ошибка вызова ИИ в roleplay_voice: {e}")
        await message.answer("Произошла ошибка. Попробуйте ещё раз.")
        return

    if show_english_reminder:
        response += "\n\nFeel free to use English!"

    # Сохраняем историю
    history.append({"role": "user", "text": text})
    history.append({"role": "assistant", "text": response})
    if len(history) > 20:
        history = history[-20:]
    user_state["roleplay_history"] = history
    set_user_state(user_id, user_state)

    await message.answer(response)