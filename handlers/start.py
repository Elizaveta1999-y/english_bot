from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from data.users import set_user_state

router = Router()

WELCOME_TEXT = (
    "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
    "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
    "Выбирай режим и начни совершенствоваться в языке!\n\n"
)

def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking"),
         InlineKeyboardButton(text="🎭 RolePlay", callback_data="start_roleplay")],
        [InlineKeyboardButton(text="📚 Lessons", callback_data="start_lessons"),
         InlineKeyboardButton(text="🗃️ Words", callback_data="start_words")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile_menu"),
         InlineKeyboardButton(text="🗣️ Language Skills", callback_data="start_skills")]
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
    set_user_state(user_id, {})
    await show_main_menu(message, edit=False)