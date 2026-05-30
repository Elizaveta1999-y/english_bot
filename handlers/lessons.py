from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import get_user_state, set_user_state

router = Router()

LEVELS = [
    ("🇦 A1 (Beginner)", "A1"),
    ("🇦 A2 (Elementary)", "A2"),
    ("🇧 B1 (Intermediate)", "B1"),
    ("🇧 B2 (Upper Intermediate)", "B2"),
    ("🇨 C1 (Advanced)", "C1")
]

@router.callback_query(lambda c: c.data == "start_lessons")
async def lessons_menu(callback: CallbackQuery):
    """Показывает меню выбора уровня и кнопку теста (редактирует текущее сообщение)"""
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["lessons"] = user_state.get("lessons", {})
    set_user_state(user_id, user_state)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"level_{code}")] for name, code in LEVELS
    ] + [
        [InlineKeyboardButton(text="📝 Пройти тест (определить уровень)", callback_data="placement_test")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "📚 <b>Режим уроков</b>\n\n"
        "Выберите свой уровень или пройдите тест, чтобы мы определили его.\n"
        "Уроки включают грамматику, лексику, чтение, письмо и говорение.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery):
    """Выбор уровня – редактирует сообщение с информацией"""
    level_code = callback.data.split("_")[1]
    level_name = dict(LEVELS).get(level_code, level_code)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к уровням", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"📖 <b>Уровень {level_name}</b>\n\n"
        "Режим в разработке. Скоро здесь появятся уроки и задания.\n"
        "Вы можете вернуться к выбору уровня или в главное меню.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "placement_test")
async def placement_test(callback: CallbackQuery):
    """Тест – редактирует сообщение"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к уровням", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "📝 <b>Тест на определение уровня</b>\n\n"
        "Функция в разработке. Скоро вы сможете пройти тест из 10-15 вопросов, "
        "и мы подберём для вас подходящий уровень.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main_from_lessons(callback: CallbackQuery):
    """Возврат в главное меню через редактирование сообщения"""
    from handlers.start import start_handler
    # Имитируем команду /start, но чтобы не создавать новое сообщение,
    # вызовем start_handler и передадим текущее сообщение?
    # Самый чистый способ: отредактировать текущее сообщение, показав главное меню.
    # Однако start_handler рассчитан на новое сообщение. Проще пересоздать меню в этом же сообщении.
    user_id = callback.from_user.id
    set_user_state(user_id, {})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking"),
         InlineKeyboardButton(text="🎭 RolePlay", callback_data="start_roleplay")],
        [InlineKeyboardButton(text="📚 Lessons", callback_data="start_lessons")]
    ])
    await callback.message.edit_text(
        "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
        "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
        "Выбирай режим и начни совершенствоваться в языке!\n\n"
        "🌟 <b>Акция</b> – полный доступ ко всему функционалу <b>399₽/мес</b>.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()