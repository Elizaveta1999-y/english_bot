from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from data.users import get_user_state, set_user_state

router = Router()

WELCOME_TEXT = (
    "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
    "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
    "Выбирай режим и начни совершенствоваться в языке!\n\n"
)

def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        # 1 строка: 📚 Уроки
        [InlineKeyboardButton(text="📚 Уроки", callback_data="start_lessons")],
        # 2 строка: 🔉Аудирование   📝Письмо
        [
            InlineKeyboardButton(text="🔉 Аудирование", callback_data="start_listening"),
            InlineKeyboardButton(text="📝 Письмо", callback_data="start_writing")
        ],
        # 3 строка: 📖 Чтение    🗣️ Говорение
        [
            InlineKeyboardButton(text="📖 Чтение", callback_data="start_reading"),
            InlineKeyboardButton(text="🗣️ Говорение", callback_data="start_govorenie")
        ],
        # 4 строка: 🔀 Грамматика
        [InlineKeyboardButton(text="🔀 Грамматика", callback_data="start_grammar")],
        # 5 строка: 🎙️Свободное общение
        [InlineKeyboardButton(text="🎙️ Свободное общение", callback_data="start_speaking")],
        # 6 строка: 🎬 Роль      🥇Лексика
        [
            InlineKeyboardButton(text="🎬 Ролевые игры", callback_data="start_roleplay"),
            InlineKeyboardButton(text="🥇 Лексика", callback_data="start_words")
        ],
        # 7 строка: 📊 Моя статистика
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="profile_menu")]
    ])

async def show_main_menu(message: Message, edit: bool = False):
    keyboard = get_main_menu_keyboard()
    if edit:
        await message.edit_text(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(WELCOME_TEXT, reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    if not state:
        set_user_state(user_id, {})
    await show_main_menu(message, edit=False)

# Обработчик для кнопок, которые ещё не реализованы (включая новые)
@router.callback_query(F.data.in_([
    "start_reading", "start_writing", "start_govorenie",
    "start_lessons", "start_grammar"
]))
async def under_construction(callback: CallbackQuery):
    await callback.answer("Этот режим в разработке. Скоро появится! 🚧", show_alert=True)