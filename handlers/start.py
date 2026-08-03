from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state
from handlers.reading import clear_all_keyboards

router = Router()

WELCOME_TEXT = (
    "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
    "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
    "Выбирай режим и начни совершенствоваться в языке!\n\n"
)

def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎙️ Общение с AI", callback_data="start_speaking"),
            InlineKeyboardButton(text="🎬 Ролевые игры", callback_data="start_roleplay")
        ],
        [
            InlineKeyboardButton(text="🔀 Грамматика", callback_data="start_grammar"),
            InlineKeyboardButton(text="🥇 Лексика", callback_data="start_words")
        ],
        [
            InlineKeyboardButton(text="🔉 Аудирование", callback_data="start_listening"),
            InlineKeyboardButton(text="📝 Письмо", callback_data="start_writing")
        ],
        [
            InlineKeyboardButton(text="📖 Чтение", callback_data="start_reading"),
            InlineKeyboardButton(text="🗣️ Говорение", callback_data="start_govorenie")
        ],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="profile_menu")]
    ])

async def show_main_menu(message: Message, edit: bool = False):
    keyboard = get_main_menu_keyboard()
    if edit:
        await message.edit_text(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    
    # Если активен режим Speaking – закрываем его
    if user_state and user_state.get("mode") == "speaking_active":
        user_state["mode"] = ""
        set_user_state(user_id, user_state)
        await state.clear()
        await message.answer("Диалог с тьютором закрыт.", reply_markup=ReplyKeyboardRemove())
    
    # Далее стандартная логика
    await clear_all_keyboards(message, state)
    if not user_state:
        set_user_state(user_id, {})
    await show_main_menu(message, edit=False)

# ---- Заглушка для режима "Уроки" ----
@router.callback_query(F.data == "start_lessons")
async def under_construction(callback: CallbackQuery):
    await callback.answer("Этот режим в разработке. Скоро появится! 🚧", show_alert=True)

# ---- Режим "Чтение" ----
@router.callback_query(F.data == "start_reading")
async def start_reading_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    from handlers.reading import start_reading
    await start_reading(callback, state)

# ---- Режим "Письмо" ----
@router.callback_query(F.data == "start_writing")
async def start_writing_mode(callback: CallbackQuery):
    await callback.answer()
    from handlers.writing import show_task_types
    await show_task_types(callback.message, edit=True)

# ---- Режим "Говорение" ----
@router.callback_query(F.data == "start_govorenie")
async def start_govorenie_mode(callback: CallbackQuery):
    await callback.answer()
    from handlers.govorenie import show_task_types
    await show_task_types(callback.message, edit=True)

# ---- Режим "Грамматика" ----
@router.callback_query(F.data == "start_grammar")
async def start_grammar_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    from handlers.grammar import enter_grammar_mode
    await enter_grammar_mode(callback.message, callback.from_user.id, state=state, edit=True)