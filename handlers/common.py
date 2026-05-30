from aiogram import Router, F
from aiogram.types import Message
from data.users import set_user_state

router = Router()

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    # Редактируем текущее сообщение, чтобы не плодить новые
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking"),
         InlineKeyboardButton(text="🎭 RolePlay", callback_data="start_roleplay")],
        [InlineKeyboardButton(text="📚 Lessons", callback_data="start_lessons")]
    ])
    await message.edit_text(
        "<b>Добро пожаловать в умный тренажер Английского языка! 🇺🇸</b>\n\n"
        "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
        "Выбирай режим и начни совершенствоваться в языке!\n\n"
        "🌟 <b>Акция</b> – полный доступ ко всему функционалу <b>399₽/мес</b>.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )