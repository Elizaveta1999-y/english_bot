import logging
import os
import random
import re
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import set_user_state, get_user_state
from services.deepseek import chat, DeepSeekError
from speaking.services.ai import process_voice_message
from speaking.services.tts import text_to_voice
from states.speaking_states import SpeakingStates
from handlers.voice import convert_to_opus, bot_texts

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

# ========== ТОЧКА ВХОДА ==========
async def start_speaking(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Emma", callback_data="speaking_voice_woman"),
         InlineKeyboardButton(text="👨 Alex", callback_data="speaking_voice_man")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text("Выбери собеседника:", reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("speaking_voice_"))
async def select_voice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    voice = callback.data.split("_")[2]
    speaker_name = "Emma" if voice == "woman" else "Alex"
    user_state = get_user_state(user_id)
    user_state["keyboard_hidden"] = False
    user_state["speaking_voice"] = voice
    user_state["speaking_speaker_name"] = speaker_name
    user_state["mode"] = "speaking_active"
    user_state["speaking_history"] = []
    user_state["russian_streak"] = 0
    user_state["feedback_prompt_msg_id"] = None
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)
    await callback.message.delete()

    msg_with_keyboard = await callback.message.answer(ENCOURAGE_TEXT, reply_markup=SPEAKING_KEYBOARD)
    user_state = get_user_state(user_id)
    user_state["speaking_keyboard_msg_id"] = msg_with_keyboard.message_id
    set_user_state(user_id, user_state)

    if user_id not in used_greetings:
        used_greetings[user_id] = []
    available = [g for g in GREETINGS if g not in used_greetings[user_id]]
    if not available:
        used_greetings[user_id] = []
        available = GREETINGS
    first_message = random.choice(available)
    used_greetings[user_id].append(first_message)

    voice_id = WOMAN_VOICE_ID if voice == "woman" else MAN_VOICE_ID
    await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action='record_voice')

    try:
        voice_path = await text_to_voice(first_message, voice_id=voice_id)
        if voice_path and os.path.exists(voice_path):
            ogg_path = convert_to_opus(voice_path)
            with open(ogg_path, 'rb') as f:
                audio_bytes = f.read()
            sent = await callback.message.answer_voice(
                BufferedInputFile(audio_bytes, filename="voice.ogg"),
                caption="",
                reply_markup=None
            )
            msg_id = sent.message_id
            if user_id not in bot_texts:
                bot_texts[user_id] = {}
            bot_texts[user_id][msg_id] = {"text": first_message, "translation": None}
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}_{msg_id}")]
            ])
            await callback.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=msg_id,
                caption="",
                reply_markup=keyboard
            )
            os.unlink(voice_path)
            os.unlink(ogg_path)
        else:
            await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        await callback.message.answer(first_message, reply_markup=SPEAKING_KEYBOARD)


# ============================================================
# ============== СОХРАНЕНИЕ ОШИБОК В ПАМЯТЬ НАСТАВНИКА ==========
# ============================================================

def _parse_speaking_json(raw: str) -> dict:
    """Парсит JSON из ответа LLM. Возвращает {} при ошибке."""
    import json as _json
    if not raw:
        return {}
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) > 1:
            s = parts[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    try:
        data = _json.loads(s)
        if isinstance(data, dict) and "feedback_html" in data:
            return data
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            try:
                data = _json.loads(s[start:end + 1])
                if isinstance(data, dict) and "feedback_html" in data:
                    return data
            except Exception:
                pass
    return {}


def _extract_quote_from_mistake(mistake: str) -> str:
    """Вытаскивает цитату студента из строки 'название — ты сказал: \"фраза\"'."""
    if not mistake:
        return ""
    m = re.search(r"ты сказал[:\s]+['«\"](.+?)['»\"]", mistake, re.IGNORECASE)
    if m:
        return m.group(1).lower().strip()
    return ""

NAME_MISTAKE_KEYWORDS = (
    "my name", "меня зовут", "твоё имя", "твое имя",
    "what's your name", "what is your name",
    "как тебя зовут", "как твоё имя", "как твое имя",
    "call me", "зови меня", "называй меня",
    "i'm alex", "i'm emma", "i am alex", "i am emma",
    "я алекс", "я эмма", "ты алекс", "ты эмма",
    "ты андрей", "теперь ты", "теперь твоё имя",
)


def _is_name_related_mistake(mistake: str) -> bool:
    """
    Проверяет, связана ли ошибка с именами/представлением/обращениями.
    Такие ошибки не должны попадать в память Наставника.
    """
    if not mistake:
        return False
    low = mistake.lower()
    return any(k in low for k in NAME_MISTAKE_KEYWORDS)



async def _save_speaking_mistakes_to_tutor_memory(
    user_id: int,
    mistakes: list,
    user_texts_all: list,
    speaker_name: str = None,
):
    """
    Сохраняет ошибки из режима «Общение с AI» прямо в память Наставника.
    - Проверяет реальность цитаты (есть ли фраза в реальных сообщениях юзера).
    - Не дублирует уже существующие ошибки.
    - Если ошибка была в done — возвращает в active.
    - Встраивает имя собеседника (Alex / Emma), чтобы Наставник
      мог сказать «общаясь с Алексом, ты сказала...».
    """
    from utils.db import tutor_get_memory, tutor_update_memory

    if not mistakes:
        return

    user_texts = [t.lower() for t in user_texts_all if t]

    memory = await tutor_get_memory(user_id)
    active = list(memory.get("active_mistakes") or [])
    done = list(memory.get("done_mistakes") or [])

    new_mistakes = []

    for raw in mistakes:
        print(f"[SPEAK-DBG] speaker_name={speaker_name!r} raw={raw!r}", flush=True)
        m = str(raw).strip()
        if not m or len(m) <= 5:
            continue
        if m.startswith("[") or m.startswith("{"):
            continue

        if _is_name_related_mistake(m):
            logger.info(f"Speaking: пропускаем ошибку про имя: {m[:60]}")
            continue

        quote = _extract_quote_from_mistake(m)
        if not quote or len(quote) < 4:
            logger.warning(f"Speaking: не удалось извлечь цитату из '{m[:60]}'")
            continue
        if not any(quote in t for t in user_texts):
            logger.warning(f"Speaking: цитата не найдена в диалоге — пропускаем: {quote[:60]}")
            continue

        # === Встраиваем имя собеседника в строку ошибки ===
        if speaker_name and "ты сказал" in m.lower():
            m = re.sub(
                r"ты\s+сказал",
                f"общаясь с {speaker_name}, ты сказал",
                m,
                count=1,
                flags=re.IGNORECASE,
            )
        # ===================================================

        if m in active:
            active.remove(m)
            active.append(m)
            continue
        if m in done:
            done.remove(m)
            active.append(m)
            continue

        new_mistakes.append(m)
    if new_mistakes:
        active.extend(new_mistakes)
        active = active[-10:]

    fields = {
        "active_mistakes": active,
        "done_mistakes": done[-20:],
        "last_session_at": int(datetime.now().timestamp()),
    }
    if not memory.get("current_mistake") and active:
        fields["current_mistake"] = active[0]

    await tutor_update_memory(user_id, **fields)


# ============================================================
# ======================== ФИДБЕК ============================
# ============================================================

@router.message(F.text == "📊 Я всё! Фидбек")
async def show_feedback(message: Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        user_state = get_user_state(user_id)
        history = user_state.get("speaking_history", [])
        user_messages = [msg for msg in history if msg.get('role') == 'user']
        count = len(user_messages)

        if count < 3:
            await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
            await message.answer("Запишите несколько голосовых сообщений, чтобы получить фидбек.")
            return

        english_messages = [msg for msg in user_messages if re.search(r'[a-zA-Z]', msg.get('text', ''))]
        if not english_messages:
            await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
            await message.answer("🗣️ Вы не использовали английский в этом диалоге.")
            return

        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

        user_texts = "\n".join([f"Пользователь: {msg['text']}" for msg in english_messages])

        prompt = (
            "Ты – опытный преподаватель английского языка. Проанализируй речь пользователя в этом диалоге.\n\n"
            "ЖЁСТКИЕ ПРАВИЛА (не нарушать!):\n"
            "1. Анализируй ТОЛЬКО сообщения пользователя на английском. Игнорируй русский язык полностью.\n"
            "2. НЕ используй приветствия, обращения (ученик, пользователь, ты и т.п.). Начинай сразу с сути.\n"
            "3. НЕ оценивай пунктуацию и заглавные буквы – только грамматику (времена, порядок слов, предлоги, артикли) и лексику (повторы, синонимы).\n"
            "4. Пунктуация (запятые, точки, вопросительные знаки) не является ошибкой и не должна упоминаться в анализе. НИКОГДА НЕ ПИШИ О ПУНКТУАЦИИ.\n"
            "5. Похвала – максимум одна короткая фраза за весь ответ, ТОЛЬКО если действительно есть за что. Если хвалить не за что – не пиши похвалу и НЕ ставь смайлик. Смайлик ставится ТОЛЬКО вместе с похвалой.\n"
            "6. НЕ предлагай практику, упражнения, дополнительные разборы. Просто дай фидбек по тому, что есть.\n"
            "7. Формат поля feedback_html: четыре пункта с жирными заголовками через HTML-теги <b>...</b>:\n"
            "   <b>Грамматика</b>\n"
            "   <b>Лексика</b>\n"
            "   <b>Общее впечатление</b> (коротко, 1–2 предложения)\n"
            "   <b>Советы</b> – максимум 3 пронумерованных совета (1., 2., 3.) в виде цитаты <blockquote>...</blockquote>.\n"
            "8. Между пунктами ставь пустую строку. Используй только HTML, без звёздочек и Markdown.\n"
            "9. Общее впечатление должно быть самостоятельным – не повторять ошибки, уже указанные в Грамматике и Лексике. Дай общую оценку беглости, разнообразию, уровню.\n"
            "10. Советы – чёткие практические советы, что именно стоит улучшить (без общих фраз).\n"
            "11. Не пиши в Общем впечатлении фразы типа 'грамматических ошибок нет' – это уже ясно из предыдущих пунктов.\n"
            "12. Если грамматических и лексических ошибок нет, то в Грамматике и Лексике напиши кратко 'Ошибок нет' и переходи к Общему впечатлению и Советам.\n"
            "13. В конце, если есть похвала, добавь её и один из смайликов: 👍🏻🤩😊👏🏻. Если похвалы нет – ничего не добавляй.\n\n"
            f"Сообщения пользователя (только английские):\n{user_texts}\n\n"
            "ВЕРНИ СТРОГО JSON без markdown:\n"
            "{\n"
            '  "feedback_html": "фидбэк для показа пользователю (HTML теги <b> и <blockquote>)",\n'
            '  "mistakes": [\n'
            '    "ТЕМА — ты сказал: \'точная фраза студента с ошибкой\'"\n'
            "  ]\n"
            "}\n\n"
            "ВАЖНО ПРО ПОЛЕ mistakes:\n"
            "Первая часть (до « — ») — это КОРОТКОЕ НАЗВАНИЕ ТЕМЫ на русском, "
            "как заголовок мини-урока. 2–5 слов. Не описание ошибки, а тема.\n\n"
            "ПРАВИЛЬНО (пиши так):\n"
            "  • «Частица to после want»\n"
            "  • «Артикль the с конкретным»\n"
            "  • «Past Simple: неправильные глаголы»\n"
            "  • «Порядок слов в вопросах»\n"
            "  • «Предлоги с travel»\n"
            "  • «Модальный глагол can»\n\n"
            "НЕПРАВИЛЬНО (НЕ пиши так):\n"
            "  ✗ «пропущена частица to»\n"
            "  ✗ «неправильно использован артикль»\n"
            "  ✗ «ошибка в порядке слов»\n"
            "  ✗ «студент забыл to»\n"
            "  ✗ «не хватает предлога»\n\n"
            "Формат целиком: «ТЕМА — ты сказал: 'фраза'».\n"
            "Пример: «Частица to после want — ты сказал: 'I want you help me'».\n\n"
            "В mistakes[] — ТОЛЬКО реальные английские ошибки пользователя с точной цитатой. "
            "Цитата ОБЯЗАТЕЛЬНО должна быть дословно из сообщений пользователя выше. "
            "Если ошибок нет — пустой массив.\n\n"
            "НИКОГДА НЕ СЧИТАЙ ОШИБКОЙ:\n"
            "• упоминание имени собеседника (Alex, Emma) в речи пользователя;\n"
            "• представление пользователя (My name is..., I'm...) — даже если грамматически странно;\n"
            "• вопросы про имена (What's your name, Who are you, Как тебя зовут);\n"
            "• обращение к собеседнику по имени.\n"
            "Это не грамматические ошибки. Не записывай их в mistakes[].\n"
            "Если пользователь ошибся в другом — запиши. Но не в именах."
        )

        thinking_msg = await message.answer("🤔 Думаю...")

        try:
            raw = await chat(prompt, max_tokens=1000, temperature=0.4)
        except DeepSeekError:
            try:
                await thinking_msg.edit_text("Сервис проверки временно недоступен. Попробуй ещё раз через минуту.")
            except Exception:
                pass
            return

        json_data = _parse_speaking_json(raw)

        if json_data:
            feedback_text = json_data.get("feedback_html") or ""
            feedback_text = feedback_text.replace('<br>', '\n').replace('<br/>', '\n')
            mistakes = json_data.get("mistakes") or []
        else:
            # Fallback: модель не вернула JSON — показываем как есть, ошибки не сохраняем
            feedback_text = raw.replace('<br>', '\n').replace('<br/>', '\n')
            mistakes = []

        user_state["pending_feedback"] = feedback_text
        user_state["pending_feedback_mistakes"] = mistakes
        set_user_state(user_id, user_state)

        if count < 6:
            try:
                await thinking_msg.delete()
            except Exception:
                pass
            await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
            await message.answer("У вас пока мало сообщений, фидбек может быть неполным.", reply_markup=ReplyKeyboardRemove())
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Показать фидбек", callback_data="show_feedback_confirm"),
                    InlineKeyboardButton(text="🗣️ Продолжить", callback_data="continue_speaking")
                ]
            ])
            sent_msg = await message.answer("Выберите действие:", reply_markup=keyboard)
            user_state["feedback_prompt_msg_id"] = sent_msg.message_id
            set_user_state(user_id, user_state)
        else:
            # Сразу показываем фидбек
            user_state["speaking_history"] = []
            user_state["pending_feedback"] = None
            user_state["pending_feedback_mistakes"] = None
            set_user_state(user_id, user_state)
            await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')

            try:
                await thinking_msg.edit_text(
                    f"📊 Фидбек по вашему диалогу:\n\n{feedback_text}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не удалось отредактировать сообщение с фидбеком: {e}")
                await message.answer("Фидбек готов:", reply_markup=ReplyKeyboardRemove())
                await message.answer(
                    f"📊 Фидбек по вашему диалогу:\n\n{feedback_text}",
                    parse_mode="HTML"
                )

            # === СОХРАНЕНИЕ ОШИБОК В ПАМЯТЬ НАСТАВНИКА ===
            if mistakes:
                try:
                    user_texts_all = [msg.get('text', '') for msg in english_messages]
                    await _save_speaking_mistakes_to_tutor_memory(
                        user_id,
                        mistakes,
                        user_texts_all,
                        speaker_name=user_state.get("speaking_speaker_name"),
                    )
                except Exception as e:
                    logger.error(f"Ошибка сохранения ошибок speaking: {e}", exc_info=True)
            # =============================================

            keyboard_msg_id = user_state.get("speaking_keyboard_msg_id")
            if keyboard_msg_id:
                try:
                    await message.bot.delete_message(message.chat.id, keyboard_msg_id)
                except Exception:
                    pass
                user_state.pop("speaking_keyboard_msg_id", None)
            user_state["mode"] = ""
            user_state["keyboard_hidden"] = True
            set_user_state(user_id, user_state)
            await state.clear()
            from handlers.start import show_main_menu
            await show_main_menu(message, edit=False)
    except Exception as e:
        logger.error(f"Ошибка в show_feedback: {e}", exc_info=True)
        await message.answer("Произошла ошибка при получении фидбека. Попробуйте позже.")

@router.callback_query(F.data == "show_feedback_confirm")
async def confirm_feedback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    feedback = user_state.get("pending_feedback")
    mistakes = user_state.get("pending_feedback_mistakes") or []
    if not feedback:
        await callback.message.edit_text("Фидбек не найден. Попробуйте запросить заново.")
        return
    await callback.message.delete()
    keyboard_msg_id = user_state.get("speaking_keyboard_msg_id")
    if keyboard_msg_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, keyboard_msg_id)
        except Exception:
            pass
        user_state.pop("speaking_keyboard_msg_id", None)

    # Собираем тексты юзера из истории ДО очистки
    history = user_state.get("speaking_history", [])
    user_texts_all = [
        msg.get('text', '')
        for msg in history
        if msg.get('role') == 'user' and re.search(r'[a-zA-Z]', msg.get('text', ''))
    ]

    user_state["speaking_history"] = []
    user_state["pending_feedback"] = None
    user_state["pending_feedback_mistakes"] = None
    user_state["mode"] = ""
    user_state["keyboard_hidden"] = True
    user_state["feedback_prompt_msg_id"] = None
    set_user_state(user_id, user_state)
    await state.clear()
    await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action='typing')
    await callback.bot.send_message(
        chat_id=callback.message.chat.id,
        text=f"📊 Фидбек по вашему диалогу:\n\n{feedback}",
        parse_mode="HTML"
    )

    # === СОХРАНЕНИЕ ОШИБОК В ПАМЯТЬ НАСТАВНИКА ===
    if mistakes:
        try:
            await _save_speaking_mistakes_to_tutor_memory(
                user_id,
                mistakes,
                user_texts_all,
                speaker_name=user_state.get("speaking_speaker_name"),
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения ошибок speaking: {e}", exc_info=True)
    # =============================================

    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=False)

@router.callback_query(F.data == "continue_speaking")
async def continue_speaking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)

    feedback_id = user_state.get("feedback_prompt_msg_id")
    if feedback_id:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=feedback_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {feedback_id}: {e}")
        user_state["feedback_prompt_msg_id"] = None

    user_state["mode"] = "speaking_active"
    user_state["keyboard_hidden"] = False
    user_state["pending_feedback"] = None
    user_state["pending_feedback_mistakes"] = None
    set_user_state(user_id, user_state)

    msg_with_keyboard = await callback.bot.send_message(
        chat_id=callback.message.chat.id,
        text="Отлично! Продолжаем 🗣️",
        reply_markup=SPEAKING_KEYBOARD
    )
    user_state = get_user_state(user_id)
    user_state["speaking_keyboard_msg_id"] = msg_with_keyboard.message_id
    set_user_state(user_id, user_state)
    await state.set_state(SpeakingStates.waiting_for_voice)

# ---------- ВАЖНО: проверка mode вынесена В ФИЛЬТР, а не внутрь ----------
@router.message(
    F.text == "🏠 Главное меню",
    lambda m: get_user_state(m.from_user.id).get("mode") == "speaking_active"
)
async def exit_speaking(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    keyboard_msg_id = user_state.get("speaking_keyboard_msg_id")
    if keyboard_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, keyboard_msg_id)
        except Exception:
            pass
        user_state.pop("speaking_keyboard_msg_id", None)
    user_state["mode"] = ""
    user_state["keyboard_hidden"] = True
    user_state["speaking_history"] = []
    user_state["russian_streak"] = 0
    user_state["pending_feedback"] = None
    user_state["pending_feedback_mistakes"] = None
    user_state["feedback_prompt_msg_id"] = None
    set_user_state(user_id, user_state)
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)

@router.message(SpeakingStates.waiting_for_voice, F.text, ~F.text.startswith('/'))
async def handle_text_in_speaking(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("feedback_prompt_msg_id"):
        return
    await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
    await message.answer("Запишите и отправьте голосовое сообщение.")

@router.message(SpeakingStates.waiting_for_voice, F.photo | F.video | F.video_note | F.animation | F.document | F.sticker)
async def handle_media_in_speaking(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("feedback_prompt_msg_id"):
        return
    await message.bot.send_chat_action(chat_id=message.chat.id, action='typing')
    await message.answer("Запишите и отправьте голосовое сообщение.")

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    keyboard_msg_id = user_state.get("speaking_keyboard_msg_id")
    if keyboard_msg_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, keyboard_msg_id)
        except Exception:
            pass
        user_state.pop("speaking_keyboard_msg_id", None)
    user_state["mode"] = ""
    user_state["keyboard_hidden"] = True
    user_state["speaking_history"] = []
    user_state["russian_streak"] = 0
    user_state["pending_feedback"] = None
    user_state["pending_feedback_mistakes"] = None
    user_state["feedback_prompt_msg_id"] = None
    set_user_state(user_id, user_state)
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)

# ---------- КНОПКИ ТЕКСТА ----------
@router.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"translate_text_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}_{msg_id}")]
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
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        try:
            translation = await chat(
                f"Переведи на русский следующий текст, верни только перевод, без кавычек и дополнительных пояснений: {text}",
                max_tokens=600,
                temperature=0.3,
            )
        except DeepSeekError:
            await callback.answer("Сервис перевода временно недоступен. Попробуйте позже.", show_alert=True)
            return
        user_texts[msg_id]["translation"] = translation
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="US", callback_data=f"show_original_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}_{msg_id}")]
        ])
        await callback.bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=translation,
            reply_markup=keyboard
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в translate_text: {e}", exc_info=True)
        await callback.answer("Ошибка.", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("show_original_"))
async def show_original(callback: CallbackQuery):
    try:
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        user_texts = bot_texts.get(user_id)
        if not user_texts or msg_id not in user_texts:
            await callback.answer("Текст не найден.", show_alert=True)
            return
        text = user_texts[msg_id]["text"]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="RUS", callback_data=f"translate_text_{user_id}_{msg_id}"),
             InlineKeyboardButton(text="Скрыть", callback_data=f"hide_text_{user_id}_{msg_id}")]
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
        parts = callback.data.split('_')
        user_id = int(parts[2])
        msg_id = int(parts[3])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Текст", callback_data=f"show_text_{user_id}_{msg_id}")]
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

# ====================== ПЕРЕХВАТЧИК КОМАНД ТОЛЬКО В СОСТОЯНИИ SPEAKING ======================
@router.message(SpeakingStates.waiting_for_voice, F.text.startswith('/') & ~F.text.in_(["/support", "/subscription", "/agreement", "/start"]))
async def handle_commands_in_speaking(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    if user_state.get("mode") != "speaking_active":
        return

    if user_state.get("feedback_prompt_msg_id"):
        return

    keyboard_msg_id = user_state.get("speaking_keyboard_msg_id")
    if keyboard_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, keyboard_msg_id)
        except Exception:
            pass
        user_state.pop("speaking_keyboard_msg_id", None)

    user_state["mode"] = ""
    user_state["keyboard_hidden"] = True
    user_state["speaking_history"] = []
    user_state["russian_streak"] = 0
    user_state["pending_feedback"] = None
    user_state["pending_feedback_mistakes"] = None
    user_state["feedback_prompt_msg_id"] = None
    set_user_state(user_id, user_state)
    await state.clear()

    await message.answer("Диалог завершен..🏁", reply_markup=ReplyKeyboardRemove())

    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)