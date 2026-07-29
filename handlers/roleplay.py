import re
import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from data.users import get_user_state, set_user_state
from services.deepseek import chat
from speaking.services.ai import process_roleplay_message

logger = logging.getLogger(__name__)
router = Router()

# ---------- Состояния для ролевой игры ----------
class RoleplayStates(StatesGroup):
    active = State()

CATEGORIES = [
    ("🏢 Работа и бизнес", "work"),
    ("✈️ Путешествия", "travel"),
    ("🍽️ Повседневная жизнь", "daily"),
    ("📚 Развлечения и хобби", "hobby"),
    ("👨‍⚕️ Здоровье", "health"),
    ("🏠 Дом и семья", "family"),
    ("📱 Технологии", "tech")
]

TOPICS = {
    # Здесь должен быть полный словарь TOPICS, он уже есть у тебя.
}

@router.callback_query(F.data == "start_roleplay")
async def start_roleplay(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.answer(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.\n\nБот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "custom_scenario")
async def custom_scenario_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "✍️ <b>Придумайте свой сценарий</b>\n\n"
        "Опишите ситуацию и роль бота одним сообщением.\n"
        "Пример:\n"
        "<i>Ты продавец в книжном магазине. Я покупатель, ищу книгу по фантастике. Ты предлагаешь новинки и помогаешь выбрать.</i>\n\n"
        "Напишите ваш сценарий:",
        parse_mode="HTML"
    )
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = True
    set_user_state(user_id, user_state)
    await state.set_state(RoleplayStates.active)  # Устанавливаем состояние для обработки текста
    await callback.answer()

@router.message(RoleplayStates.active, F.text)
async def handle_custom_scenario_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if not user_state.get("awaiting_custom_scenario"):
        return  # Если не ждём сценарий, то это обычное сообщение в игре

    custom_prompt = message.text
    user_state["awaiting_custom_scenario"] = False
    user_state["mode"] = "roleplay_active"
    user_state["history"] = []
    user_state["roleplay_custom_scenario"] = custom_prompt
    set_user_state(user_id, user_state)

    await message.answer(
        f"🎬 <b>Сценарий принят!</b>\n\n"
        f"Ситуация: {custom_prompt}\n\n"
        f"Теперь вы можете начать диалог. Говорите голосом или пишите текст.",
        parse_mode="HTML"
    )
    # Можно сразу дать клавиатуру ролевой игры
    await show_roleplay_keyboard(message)

@router.callback_query(F.data == "retry_custom_scenario")
async def retry_custom_scenario(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = True
    set_user_state(user_id, user_state)
    await state.set_state(RoleplayStates.active)
    await callback.message.answer(
        "✍️ <b>Придумайте свой сценарий</b>\n\n"
        "Опишите ситуацию и роль бота одним сообщением.\n"
        "Пример:\n"
        "<i>Ты продавец в книжном магазине. Я покупатель, ищу книгу по фантастике.</i>\n\n"
        "Напишите ваш сценарий:",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_categories_from_scenario")
async def back_to_categories_from_scenario(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = False
    set_user_state(user_id, user_state)
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.answer(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cat_"))
async def show_topics(callback: CallbackQuery):
    cat_id = callback.data[4:]
    topics_list = TOPICS.get(cat_id, [])
    if not topics_list:
        await callback.answer("Нет тем в этой категории", show_alert=True)
        return
    buttons = []
    for idx, topic_info in enumerate(topics_list):
        buttons.append([InlineKeyboardButton(text=topic_info["name"], callback_data=f"topic_{cat_id}_{idx}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories")])
    topics_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    cat_display = next((c[0] for c in CATEGORIES if c[1] == cat_id), cat_id)
    await callback.message.edit_text(f"🎭 <b>{cat_display}</b>\n\nВыберите тему:", reply_markup=topics_keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.edit_text("🎭 <b>Выберите категорию</b> или создайте свой сценарий.", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("topic_"))
async def topic_chosen(callback: CallbackQuery, state: FSMContext):
    _, cat_id, idx_str = callback.data.split("_")
    idx = int(idx_str)
    topics_list = TOPICS.get(cat_id, [])
    if idx >= len(topics_list):
        await callback.answer("Тема не найдена", show_alert=True)
        return
    topic_info = topics_list[idx]
    topic = topic_info["name"]
    description = topic_info["description"]
    goals = topic_info["goals"]
    user_id = callback.from_user.id

    # Сохраняем состояние в user_state
    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": cat_id,
        "roleplay_custom_scenario": None,
        "awaiting_custom_scenario": False
    })

    # Устанавливаем FSM-состояние
    await state.set_state(RoleplayStates.active)

    await callback.answer(f"Выбрана тема: {topic}")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Завершить диалог")]
        ],
        resize_keyboard=True
    )
    goals_text = "\n".join([f"{i+1}) {goal}" for i, goal in enumerate(goals)])
    roleplay_info = (
        f"🎭 <b>Ролевая игра: {topic}</b>\n\n"
        f"📖 Ситуация: {description}\n\n"
        f"🎯 Ваши цели:\n{goals_text}\n\n"
        f"🗣️ <b>Говорите голосом или пишите текстом.</b>\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?».\n"
        f"Когда закончите, нажмите «📊 Завершить диалог» для анализа."
    )
    await callback.message.edit_text(roleplay_info, parse_mode="HTML")
    await callback.message.answer("🎬 <b>Можете начинать!</b>", reply_markup=keyboard, parse_mode="HTML")

# ---------- Обработчик текстовых сообщений в активной ролевой игре ----------
@router.message(RoleplayStates.active, F.text)
async def handle_roleplay_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)

    # Если мы в режиме ожидания кастомного сценария, то это уже обработано выше
    if user_state.get("awaiting_custom_scenario"):
        # Это уже перехвачено отдельным хендлером, но если вдруг сюда попало - пропускаем
        return

    if user_state.get("mode") != "roleplay_active":
        return  # Не в ролевой игре

    user_text = message.text

    # Обрабатываем через ИИ
    try:
        ai_response = await process_roleplay_message(user_id, user_text)
    except Exception as e:
        logger.error(f"Ошибка в ролевой игре: {e}")
        await message.answer("Произошла ошибка. Попробуйте ещё раз.")
        return

    # Сохраняем историю
    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    # Отправляем ответ
    await message.answer(ai_response)

# ---------- Обработчик кнопки "💡 Что ответить?" ----------
@router.message(RoleplayStates.active, F.text == "💡 Что ответить?")
async def give_hint(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("history", [])
    # Последнее сообщение бота (если есть)
    last_bot_msg = None
    if history and history[-1].get("role") == "assistant":
        last_bot_msg = history[-1].get("text", "")
    prompt = (
        "Ты – помощник в ролевой игре. Пользователь просит подсказку, что можно ответить дальше.\n"
        f"Контекст диалога (последние сообщения):\n{history[-5:] if history else 'Нет истории'}\n"
        f"Последнее сообщение бота: {last_bot_msg or 'Нет сообщения'}\n"
        "Предложи 2–3 варианта того, что пользователь может сказать или спросить в этой ситуации.\n"
        "Ответы должны быть на русском, естественные, соответствовать роли и ситуации."
    )
    try:
        hint = await chat(prompt, max_tokens=200, temperature=0.7)
    except Exception as e:
        logger.error(f"Ошибка получения подсказки: {e}")
        await message.answer("Не удалось получить подсказку. Попробуйте позже.")
        return
    await message.answer(f"💡 <b>Идеи для ответа:</b>\n\n{hint}", parse_mode="HTML")

# ---------- Обработчик кнопки "🏠 Главное меню" в ролевой игре ----------
@router.message(RoleplayStates.active, F.text == "🏠 Главное меню")
async def exit_to_main_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    user_state["history"] = []
    set_user_state(user_id, user_state)
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)

# ---------- Обработчик кнопки "📊 Завершить диалог" ----------
@router.message(RoleplayStates.active, F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("history", [])
    if not history:
        await message.answer("Вы пока ничего не сказали. Начните разговор!", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    # Анализируем диалог через ИИ
    history_text = "\n".join([f"{msg['role']}: {msg['text']}" for msg in history if msg['role'] in ['user', 'assistant']])
    prompt = (
        "Ты – языковой тренер. Проанализируй диалог пользователя с ИИ в ролевой игре и дай краткий фидбек:\n"
        "- Грамматика (2-3 основные ошибки с исправлениями)\n"
        "- Лексика (удачные фразы, что можно улучшить)\n"
        "- Достижение целей (насколько пользователь справился с задачей)\n"
        "Будь конструктивным, обращайся на 'ты'.\n\n"
        f"Диалог:\n{history_text}"
    )
    try:
        feedback = await chat(prompt, max_tokens=400, temperature=0.5)
    except Exception as e:
        logger.error(f"Ошибка получения фидбека: {e}")
        await message.answer("Не удалось получить фидбек. Попробуйте позже.")
        return

    # Очищаем состояние
    user_state["mode"] = ""
    user_state["history"] = []
    set_user_state(user_id, user_state)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Начать новую игру", callback_data="start_roleplay")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await message.answer(f"📊 <b>Фидбек по диалогу:</b>\n\n{feedback}", reply_markup=keyboard, parse_mode="HTML")
    await message.answer("Ролевая игра завершена.", reply_markup=ReplyKeyboardRemove())

# ---------- Вспомогательная функция для клавиатуры ----------
async def show_roleplay_keyboard(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Завершить диалог")]
        ],
        resize_keyboard=True
    )
    await message.answer("Доступные действия:", reply_markup=keyboard)