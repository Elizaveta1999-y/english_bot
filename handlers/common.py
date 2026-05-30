from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from data.users import set_user_state

router = Router()

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    from handlers.start import start_handler

    await start_handler(message)