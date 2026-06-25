# handlers/skills.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from data.users import get_user_state, set_user_state
from data.reading_tasks import READING_TASKS
from services.deepseek import chat
from speaking.services.stt import voice_to_text
from speaking.services.tts import text_to_voice
import random
import re

router = Router()

# ---------- FSM для письма и говорения ----------
class WritingStates(StatesGroup):
    waiting_for_text = State()

class SpeakingStates(StatesGroup):
    waiting_for_voice = State()

# ---------- Вспомогательные функции ----------
def get_skills_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎧 Аудирование", callback_data="skill_listening"),
         InlineKeyboardButton(text="📖 Чтение", callback_data="skill_reading")],
        [InlineKeyboardButton(text="✍️ Письмо", callback_data="skill_writing"),
         InlineKeyboardButton(text="🗣️ Говорение", callback_data="skill_speaking")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_limited_access_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оформить подписку (900 ₽/мес)", callback_data="profile_extend")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_skills")]
    ])

def check_access(user_id: int) -> tuple:
    """
    Проверяет доступ пользователя к режиму Language Skills.
    Возвращает (разрешено_ли, сообщение_при_отказе)
    """
    state = get_user_state(user_id)
    now = datetime.now()
    
    # Проверяем регистрационную дату
    reg_date_str = state.get("registration_date")
    if not reg_date_str:
        # Первый запуск — сохраняем дату
        state["registration_date"] = now.isoformat()
        set_user_state(user_id, state)
        return True, None
    
    reg_date = datetime.fromisoformat(reg_date_str)
    hours_since_reg = (now - reg_date).total_seconds() / 3600
    
    # Если прошло менее 48 часов — полный доступ
    if hours_since_reg < 48:
        return True, None
    
    # Проверяем подписку
    sub = state.get("profile", {}).get("subscription", {})
    if sub.get("active"):
        return True, None
    
    # Проверяем дневной лимит (3 задания)
    today = now.date().isoformat()
    daily_skills = state.get("daily_skills_count", 0)
    last_skill_date = state.get("last_skill_date")
    
    if last_skill_date != today:
        # Новый день — сбрасываем счётчик
        daily_skills = 0
        state["daily_skills_count"] = 0
        state["last_skill_date"] = today
        set_user_state(user_id, state)
        return True, None
    
    if daily_skills < 3:
        return True, None
    else:
        return False, "🔒 Вы исчерпали дневной лимит. Оформите подписку для неограниченного доступа."

def increment_skill_counter(user_id: int):
    """Увеличивает счётчик выполненных заданий в день"""
    state = get_user_state(user_id)
    today = datetime.now().date().isoformat()
    last_date = state.get("last_skill_date")
    if last_date != today:
        state["daily_skills_count"] = 1
        state["last_skill_date"] = today
    else:
        state["daily_skills_count"] = state.get("daily_skills_count", 0) + 1
    set_user_state(user_id, state)

# ---------- Главное меню навыков ----------
@router.callback_query(lambda c: c.data == "start_skills")
async def start_skills(callback: CallbackQuery):
    user_id = callback.from_user.id
    # Проверяем доступ (для входа в меню доступ всегда открыт)
    await callback.message.edit_text(
        "🗣️ <b>Language Skills</b>\n\n"
        "Практикуйте четыре ключевых навыка языка: аудирование, чтение, письмо и говорение.\n"
        "Задания построены по аналогии с экзаменами ОГЭ и ЕГЭ — тренируйтесь в формате, приближенном к реальному.\n\n"
        "Выберите навык:",
        reply_markup=get_skills_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- 1. ЧТЕНИЕ ----------
@router.callback_query(lambda c: c.data == "skill_reading")
async def skill_reading(callback: CallbackQuery):
    user_id = callback.from_user.id
    allowed, msg = check_access(user_id)
    if not allowed:
        await callback.message.edit_text(
            f"{msg}\n\nЧтобы получить неограниченный доступ, оформите подписку.",
            reply_markup=get_limited_access_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    tasks = READING_TASKS
    if not tasks:
        await callback.message.edit_text("📭 Заданий пока нет. Зайдите позже.")
        await callback.answer()
        return
    
    task = random.choice(tasks)
    state = get_user_state(user_id)
    state["current_reading_task"] = task
    set_user_state(user_id, state)
    
    # Формируем текст
    text = f"📖 <b>Чтение</b>\n\n{task['text']}\n\n"
    for i, q in enumerate(task['questions'], 1):
        text += f"{i}. {q['question']}\n"
        if q['type'] == 'choice':
            for idx, opt in enumerate(q['options'], 1):
                text += f"   {chr(64+idx)}) {opt}\n"
        text += "\n"
    text += "Введите номера ответов (через запятую или пробел), например: 1A, 2B, 3C"
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

@router.message(F.text, lambda msg: get_user_state(msg.from_user.id).get("current_reading_task"))
async def reading_answer(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    task = state.get("current_reading_task")
    if not task:
        return
    
    # Считаем выполненное задание
    increment_skill_counter(user_id)
    
    # Парсим ответы
    raw = message.text.strip().upper().replace(" ", "")
    parts = re.split(r'[,;\s]+', raw)
    user_answers = {}
    for part in parts:
        if len(part) >= 2:
            num = part[:-1]
            letter = part[-1]
            if num.isdigit() and letter in "ABCD":
                user_answers[int(num)] = letter
    correct_count = 0
    feedback = []
    for i, q in enumerate(task['questions'], 1):
        correct = q['correct']
        if q['type'] == 'choice':
            if i in user_answers and user_answers[i] == correct:
                correct_count += 1
                feedback.append(f"✅ {i}. {q['question']} — верно")
            else:
                correct_letter = correct
                correct_text = next((opt for idx, opt in enumerate(q['options']) if chr(65+idx) == correct), "")
                feedback.append(f"❌ {i}. {q['question']} — правильно: {correct_letter}) {correct_text}")
        elif q['type'] == 'true_false':
            user_ans = user_answers.get(i, "")
            if user_ans == "T" or user_ans == "TRUE":
                user_ans = "True"
            elif user_ans == "F" or user_ans == "FALSE":
                user_ans = "False"
            if user_ans == correct:
                correct_count += 1
                feedback.append(f"✅ {i}. {q['question']} — верно")
            else:
                feedback.append(f"❌ {i}. {q['question']} — правильно: {correct}")
        elif q['type'] == 'fill':
            # Для fill-blank ждём слово (упрощённо)
            user_word = message.text.strip().split()[-1]
            if user_word.lower() == correct.lower():
                correct_count += 1
                feedback.append(f"✅ {i}. {q['question']} — верно")
            else:
                feedback.append(f"❌ {i}. {q['question']} — правильно: {correct}")
    
    total = len(task['questions'])
    result = f"📊 <b>Результат</b>: {correct_count} из {total}\n\n" + "\n".join(feedback)
    await message.answer(result, parse_mode="HTML")
    
    del state["current_reading_task"]
    set_user_state(user_id, state)

# ---------- 2. АУДИРОВАНИЕ ----------
@router.callback_query(lambda c: c.data == "skill_listening")
async def skill_listening(callback: CallbackQuery):
    user_id = callback.from_user.id
    allowed, msg = check_access(user_id)
    if not allowed:
        await callback.message.edit_text(
            f"{msg}\n\nЧтобы получить неограниченный доступ, оформите подписку.",
            reply_markup=get_limited_access_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🎧 <b>Аудирование</b>\n\n"
        "В разработке. Скоро здесь появятся задания на понимание речи.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start_skills")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- 3. ПИСЬМО ----------
@router.callback_query(lambda c: c.data == "skill_writing")
async def skill_writing(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    allowed, msg = check_access(user_id)
    if not allowed:
        await callback.message.edit_text(
            f"{msg}\n\nЧтобы получить неограниченный доступ, оформите подписку.",
            reply_markup=get_limited_access_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    topics = [
        "Напишите письмо другу (100–120 слов) на тему: «Мои летние каникулы».",
        "Напишите эссе (150–200 слов) на тему: «Преимущества и недостатки интернета».",
        "Опишите свою любимую книгу или фильм (100–120 слов).",
        "Напишите рассказ (100–150 слов) на тему: «Неожиданная встреча»."
    ]
    topic = random.choice(topics)
    await callback.message.edit_text(
        f"✍️ <b>Письмо</b>\n\nЗадание:\n{topic}\n\n"
        "Напишите текст, а затем отправьте его в чат. Я проверю вашу работу.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start_skills")]
        ]),
        parse_mode="HTML"
    )
    await state.set_state(WritingStates.waiting_for_text)
    await state.update_data(topic=topic)
    await callback.answer()

@router.message(WritingStates.waiting_for_text)
async def writing_submit(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    if len(text) < 20:
        await message.answer("Текст слишком короткий. Напишите хотя бы 20 слов.")
        return
    
    increment_skill_counter(user_id)
    
    data = await state.get_data()
    topic = data.get("topic", "")
    prompt = f"""
Ты эксперт по английскому языку. Проверь текст по следующим критериям:
- Грамматика
- Лексика
- Структура
- Соответствие теме
Дай оценку по 5-балльной шкале и напиши рекомендации (3–5 предложений).
Тема: {topic}
Текст: {text}
"""
    await message.answer("🔄 Проверяю...")
    feedback = chat(prompt, max_tokens=500, temperature=0.4)
    await message.answer(f"📊 <b>Результат</b>:\n\n{feedback}", parse_mode="HTML")
    await state.clear()

# ---------- 4. ГОВОРЕНИЕ ----------
@router.callback_query(lambda c: c.data == "skill_speaking")
async def skill_speaking(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    allowed, msg = check_access(user_id)
    if not allowed:
        await callback.message.edit_text(
            f"{msg}\n\nЧтобы получить неограниченный доступ, оформите подписку.",
            reply_markup=get_limited_access_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    topics = [
        "Опишите вашу любимую фотографию (5–7 предложений).",
        "Расскажите о своем хобби (5–7 предложений).",
        "Опишите свой типичный день (5–7 предложений)."
    ]
    topic = random.choice(topics)
    await callback.message.edit_text(
        f"🗣️ <b>Говорение</b>\n\nЗадание:\n{topic}\n\n"
        "Запишите голосовое сообщение и отправьте его. Я проанализирую вашу речь.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start_skills")]
        ]),
        parse_mode="HTML"
    )
    await state.set_state(SpeakingStates.waiting_for_voice)
    await state.update_data(topic=topic)
    await callback.answer()

@router.message(SpeakingStates.waiting_for_voice, F.voice)
async def speaking_submit(message: Message, state: FSMContext):
    user_id = message.from_user.id
    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())
    if not user_text:
        await message.answer("Не удалось распознать речь. Попробуйте ещё раз.")
        return
    
    increment_skill_counter(user_id)
    
    data = await state.get_data()
    topic = data.get("topic", "")
    prompt = f"""
Ты эксперт по английскому языку. Оцени ответ по следующим критериям:
- Грамматика
- Лексика
- Соответствие теме
- Беглость (насколько связно)
Дай оценку по 5-балльной шкале и напиши рекомендации (3–5 предложений).
Тема: {topic}
Ответ: {user_text}
"""
    await message.answer("🔄 Анализирую...")
    feedback = chat(prompt, max_tokens=500, temperature=0.4)
    await message.answer(f"📊 <b>Результат</b>:\n\n{feedback}", parse_mode="HTML")
    await state.clear()