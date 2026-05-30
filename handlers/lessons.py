from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import get_user_state, set_user_state

router = Router()

# Список уровней
LEVELS = [
    ("🇦 A1 (Beginner)", "A1"),
    ("🇦 A2 (Elementary)", "A2"),
    ("🇧 B1 (Intermediate)", "B1"),
    ("🇧 B2 (Upper Intermediate)", "B2"),
    ("🇨 C1 (Advanced)", "C1")
]

@router.callback_query(lambda c: c.data == "start_lessons")
async def lessons_menu(callback: CallbackQuery):
    """Показывает меню выбора уровня и кнопку теста"""
    user_id = callback.from_user.id
    # Сбрасываем предыдущее состояние уроков (опционально)
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
    """Выбор уровня – пока заглушка"""
    level_code = callback.data.split("_")[1]
    level_name = dict(LEVELS).get(level_code, level_code)
    await callback.message.answer(
        f"📖 <b>Уровень {level_name}</b>\n\n"
        "Режим в разработке. Скоро здесь появятся уроки и задания.\n"
        "Пока что вы можете вернуться в главное меню.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "placement_test")
async def placement_test(callback: CallbackQuery):
    """Тест на определение уровня – заглушка"""
    await callback.message.answer(
        "📝 <b>Тест на определение уровня</b>\n\n"
        "Функция в разработке. Скоро вы сможете пройти тест из 10-15 вопросов, "
        "и мы подберём для вас подходящий уровень.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main_from_lessons(callback: CallbackQuery):
    """Возврат в главное меню"""
    from handlers.start import start_handler
    # Создаём объект Message из callback, чтобы передать в start_handler
    # Проще: отправить новое сообщение с /start, но лучше вызвать start_handler с фейковым message
    # Для простоты: отвечаем текстом и предлагаем нажать /start
    await callback.message.answer("🏠 Возврат в главное меню. Нажмите /start")
    await callback.answer()