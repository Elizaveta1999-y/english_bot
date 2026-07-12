import re
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
from services.deepseek import chat
from speaking.services.ai import is_safe_message, process_roleplay_message

router = Router()

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
    # Здесь должен быть полный словарь TOPICS, я не буду его дублировать из-за размера, он уже есть у тебя.
}

@router.callback_query(lambda c: c.data == "start_roleplay")
async def start_roleplay(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.answer(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.\n\nБот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "custom_scenario")
async def custom_scenario_start(callback: CallbackQuery):
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
    await callback.answer()

@router.callback_query(lambda c: c.data == "retry_custom_scenario")
async def retry_custom_scenario(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = True
    set_user_state(user_id, user_state)
    await callback.message.answer(
        "✍️ <b>Придумайте свой сценарий</b>\n\n"
        "Опишите ситуацию и роль бота одним сообщением.\n"
        "Пример:\n"
        "<i>Ты продавец в книжном магазине. Я покупатель, ищу книгу по фантастике.</i>\n\n"
        "Напишите ваш сценарий:",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_categories_from_scenario")
async def back_to_categories_from_scenario(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = False
    set_user_state(user_id, user_state)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.answer(
        "🎭 <b>Выберите категорию</b> или создайте свой сценарий.",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("cat_"))
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

@router.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.edit_text("🎭 <b>Выберите категорию</b> или создайте свой сценарий.", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("topic_"))
async def topic_chosen(callback: CallbackQuery):
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
    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": cat_id
    })
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

@router.callback_query(lambda c: c.data == "continue_roleplay")
async def continue_roleplay(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Продолжаем.")

@router.callback_query(lambda c: c.data == "exit_to_menu")
async def exit_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    await callback.message.answer("Режим завершён. Нажмите /start для выбора режима.", reply_markup=ReplyKeyboardRemove())
    await callback.answer()