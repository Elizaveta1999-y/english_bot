# handlers/skills.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from data.users import get_user_state, set_user_state
from data.reading_tasks import READING_TASKS  # банк заданий для чтения
from services.deepseek import chat
from speaking.services.stt import voice_to_text
from speaking.services.tts import text_to_voice
import random

router = Router()

# ---------- FSM для письма и говорения ----------
class WritingStates(StatesGroup):
    waiting_for_text = State()

class SpeakingStates(StatesGroup):
    waiting_for_voice = State()

# ---------- Вспомогательные функции ----------
def get_skills_keyboard():
    """Клавиатура выбора навыка"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎧 Аудирование", callback_data="skill_listening"),
         InlineKeyboardButton(text="📖 Чтение", callback_data="skill_reading")],
        [InlineKeyboardButton(text="✍️ Письмо", callback_data="skill_writing"),
         InlineKeyboardButton(text="🗣️ Говорение", callback_data="skill_speaking")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def check_subscription(user_id: int) -> bool:
    """Проверяет, активна ли подписка у пользователя."""
    state = get_user_state(user_id)
    sub = state.get("profile", {}).get("subscription", {})
    return sub.get("active", False)

# ---------- Главное меню навыков ----------
@router.callback_query(lambda c: c.data == "start_skills")
async def start_skills(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_subscription(user_id):
        await callback.message.edit_text(
            "🔒 <b>Доступ к тренажёрам Language Skills</b>\n\n"
            "Этот режим доступен только по подписке.\n"
            "Оформите подписку, чтобы тренировать все четыре навыка: аудирование, чтение, письмо и говорение.\n\n"
            "💳 <b>Подписка</b> — 399 ₽/мес.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оформить подписку", callback_data="profile_extend")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
            ]),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗣️ <b>Language Skills</b>\n\n"
        "Практикуйте четыре ключевых навыка языка: аудирование, чтение, письмо и говорение.\n"
        "Задания построены по аналогии с экзаменами ОГЭ и ЕГЭ — тренируйтесь в формате, приближенном к реальному.\n\n"
        "Выберите навык:",
        reply_markup=get_skills_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- 1. ЧТЕНИЕ (полностью детерминированное) ----------
@router.callback_query(lambda c: c.data == "skill_reading")
async def skill_reading(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not check_subscription(user_id):
        await callback.answer("Доступно только по подписке", show_alert=True)
        return
    
    # Выбираем случайное задание из банка
    tasks = READING_TASKS
    if not tasks:
        await callback.message.edit_text("📭 Заданий пока нет. Зайдите позже.")
        await callback.answer()
        return
    
    task = random.choice(tasks)
    # Сохраняем в состояние пользователя текущее задание
    state = get_user_state(user_id)
    state["current_reading_task"] = task
    set_user_state(user_id, state)
    
    # Формируем сообщение: текст + вопросы
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

# Обработчик ответов на чтение (детерминированная проверка)
@router.message(F.text, lambda msg: get_user_state(msg.from_user.id).get("current_reading_task"))
async def reading_answer(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    task = state.get("current_reading_task")
    if not task:
        return
    
    # Парсим ответы пользователя (ожидаем: "1A, 2B, 3C" или "1 A 2 B")
    raw = message.text.strip().upper().replace(" ", "")
    # Разбиваем по запятым или пробелам
    import re
    parts = re.split(r'[,;\s]+', raw)
    user_answers = {}
    for part in parts:
        if len(part) >= 2:
            num = part[:-1]
            letter = part[-1]
            if num.isdigit() and letter in "ABCD":
                user_answers[int(num)] = letter
    # Проверяем
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
            # Для fill-blank ждём слово
            user_word = message.text.strip().split()[-1]  # упрощённо
            if user_word.lower() == correct.lower():
                correct_count += 1
                feedback.append(f"✅ {i}. {q['question']} — верно")
            else:
                feedback.append(f"❌ {i}. {q['question']} — правильно: {correct}")
    
    total = len(task['questions'])
    result = f"📊 <b>Результат</b>: {correct_count} из {total}\n\n" + "\n".join(feedback)
    await message.answer(result, parse_mode="HTML")
    
    # Очищаем состояние
    del state["current_reading_task"]
    set_user_state(user_id, state)

# ---------- 2. АУДИРОВАНИЕ (пока заглушка) ----------
@router.callback_query(lambda c: c.data == "skill_listening")
async def skill_listening(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎧 <b>Аудирование</b>\n\n"
        "В разработке. Скоро здесь появятся задания на понимание речи.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start_skills")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- 3. ПИСЬМО (ИИ-проверка) ----------
@router.callback_query(lambda c: c.data == "skill_writing")
async def skill_writing(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not check_subscription(user_id):
        await callback.answer("Доступно только по подписке", show_alert=True)
        return
    
    # Даём тему
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
    
    # Проверяем через DeepSeek
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

# ---------- 4. ГОВОРЕНИЕ (ИИ-проверка + STT) ----------
@router.callback_query(lambda c: c.data == "skill_speaking")
async def skill_speaking(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not check_subscription(user_id):
        await callback.answer("Доступно только по подписке", show_alert=True)
        return
    
    # Даём тему
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