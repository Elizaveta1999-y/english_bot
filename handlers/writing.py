import json
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Создаем состояния для машины состояний (FSM)
class WritingStates(StatesGroup):
    choosing_type = State()      # Шаг 1: выбор типа задания
    choosing_level = State()     # Шаг 2: выбор уровня
    waiting_answer = State()     # Шаг 3: ожидаем текст от пользователя

router = Router()

# --- ВРЕМЕННАЯ БАЗА ЗАДАНИЙ (пока заглушка, потом вынесем в JSON) ---
MOCK_TASKS = [
    {"id": 1, "type": "email", "level": "beginner", "task_text": "Напиши письмо другу о каникулах...", "keywords": ["holiday", "beach"]},
    {"id": 2, "type": "post", "level": "beginner", "task_text": "Напиши пост о завтраке...", "keywords": ["breakfast", "tasty"]},
    {"id": 3, "type": "story", "level": "beginner", "task_text": "Напиши историю про собаку и дождь...", "keywords": ["dog", "rain"]},
]

# --- Клавиатура выбора типа задания ---
def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📧 Email", callback_data="type_email"),
            InlineKeyboardButton(text="📝 Эссе", callback_data="type_essay")
        ],
        [
            InlineKeyboardButton(text="📱 Пост в соцсети", callback_data="type_post"),
            InlineKeyboardButton(text="💬 Диалог", callback_data="type_dialogue")
        ],
        [
            InlineKeyboardButton(text="📊 Данные/График", callback_data="type_data"),
            InlineKeyboardButton(text="📖 История", callback_data="type_story")
        ],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])

# --- Клавиатура выбора уровня ---
def get_levels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌱 Новичок", callback_data="level_beginner"),
            InlineKeyboardButton(text="🔥 Любитель", callback_data="level_intermediate")
        ],
        [
            InlineKeyboardButton(text="🧠 Эксперт", callback_data="level_advanced"),
            InlineKeyboardButton(text="🔙 Назад к типам", callback_data="back_to_types")
        ]
    ])

# --- Функция показа типов (вызывается из главного меню) ---
async def show_task_types(message: Message, edit: bool = False):
    text = (
        "✍️ *Режим Письмо*\n\n"
        "Выберите тип задания, которое хотите выполнить:\n"
        "📧 *Email* — письмо другу или коллеге\n"
        "📝 *Эссе* — выражение своего мнения\n"
        "📱 *Пост* — подпись для соцсетей\n"
        "💬 *Диалог* — сценарий разговора\n"
        "📊 *Данные* — описание графиков\n"
        "📖 *История* — рассказ по ключевым словам"
    )
    keyboard = get_types_keyboard()
    
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# --- Обработчик выбора ТИПА ---
@router.callback_query(F.data.startswith("type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Сохраняем выбранный тип в память (FSM)
    task_type = callback.data.split("_")[1]  # email, post, story и т.д.
    await state.update_data(task_type=task_type)
    
    # Переключаем состояние на выбор уровня
    await state.set_state(WritingStates.choosing_level)
    
    text = f"Вы выбрали тип: *{task_type.upper()}*.\nТеперь выберите уровень сложности:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

# --- Обработчик выбора УРОВНЯ ---
@router.callback_query(F.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Сохраняем уровень
    level = callback.data.split("_")[1]  # beginner, intermediate, advanced
    await state.update_data(level=level)
    
    # --- Ищем задание в БАНКЕ (пока из MOCK_TASKS) ---
    user_data = await state.get_data()
    task_type = user_data.get("task_type")
    
    # Фильтруем задания по типу и уровню
    suitable_tasks = [t for t in MOCK_TASKS if t["type"] == task_type and t["level"] == level]
    
    if not suitable_tasks:
        # Если нет подходящего (заглушка)
        task_text = f"Задание для {task_type} уровня {level} пока в разработке, но вот тестовое: Напиши 3 предложения о погоде."
        keywords = ["weather", "sun", "rain"]
    else:
        task = random.choice(suitable_tasks)
        task_text = task["task_text"]
        keywords = task["keywords"]
    
    # Сохраняем задание и ключевые слова в память (пригодятся для проверки ИИ)
    await state.update_data(task_text=task_text, keywords=keywords)
    
    # Формируем красивое сообщение с заданием
    message_text = (
        f"📝 *Ваше задание:*\n\n{task_text}\n\n"
        f"🔑 *Подсказка:* используйте слова: {', '.join(keywords)}\n"
        f"📏 Пишите кратко (до 50 слов).\n\n"
        f"✍️ Напишите свой ответ в чат одним сообщением."
    )
    
    # Кнопка "Отмена", чтобы выйти из режима
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Отменить задание", callback_data="cancel_writing")]
    ])
    
    await callback.message.edit_text(message_text, reply_markup=cancel_keyboard, parse_mode="Markdown")
    
    # Переключаем состояние в режим ожидания текста
    await state.set_state(WritingStates.waiting_answer)

# --- Обработчик получения ТЕКСТА от пользователя (главная проверка) ---
@router.message(WritingStates.waiting_answer, F.text)
async def handle_user_answer(message: Message, state: FSMContext):
    user_text = message.text
    
    # 1. Пре-фильтр на бэкенде (экономия токенов!)
    word_count = len(user_text.split())
    if word_count < 3:
        await message.answer("❌ Слишком коротко! Напишите хотя бы 3-4 предложения, чтобы я мог проверить ваш уровень.")
        return
    if word_count > 70:  # Защита от гигантских текстов для новичков
        await message.answer("⚠️ Слишком длинно! Сократите ответ до 50-60 слов, чтобы я мог качественно проверить.")
        return
    
    # 2. Проверяем, есть ли ключевые слова (грубо, без ИИ)
    data = await state.get_data()
    keywords = data.get("keywords", [])
    has_keyword = any(kw in user_text.lower() for kw in keywords)
    
    if not has_keyword:
        await message.answer(
            f"🤔 Вы написали хороший текст, но я не вижу ключевых слов: *{', '.join(keywords)}*.\n"
            f"Попробуйте перефразировать ответ с этими словами, чтобы тема была раскрыта.",
            parse_mode="Markdown"
        )
        # Не сбрасываем состояние, даем шанс переписать
        return
    
    # 3. Здесь будет отправка в DeepSeek (ПОКА ЗАГЛУШКА)
    # Вместо ИИ отправляем заглушку, чтобы вы увидели логику
    await message.answer(
        "✅ *Отлично! Текст принят.*\n\n"
        "🤖 *ИИ-проверка (заглушка):*\n"
        "Ваш текст содержит ключевые слова и достаточен по объему.\n\n"
        "📊 *Результат:* 5/6 баллов.\n"
        "✍️ *Исправленный вариант:* " + user_text.replace("cook", "cooked").replace("go", "went") + "\n\n"
        "*(В ближайшее время здесь появится полноценная проверка через DeepSeek!)*\n\n"
        "Хотите попробовать еще раз? Нажмите /start и зайдите в режим снова.",
        parse_mode="Markdown"
    )
    
    # Очищаем состояние, чтобы завершить сессию
    await state.clear()

# --- Обработчик ОТМЕНЫ ---
@router.callback_query(F.data == "cancel_writing")
async def cancel_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    # Возвращаем в главное меню (импортируем функцию из основного файла)
    from handlers.main_menu import show_main_menu  # Укажите ваш реальный путь
    await show_main_menu(callback.message, edit=True)

# --- Обработчик кнопки "Назад к типам" ---
@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)

# --- Обработчик кнопки "Назад в меню" ---
@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    from handlers.main_menu import show_main_menu
    await show_main_menu(callback.message, edit=True)