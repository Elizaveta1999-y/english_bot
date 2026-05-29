from aiogram import Router, F
from aiogram.types import Message
from data.users import get_user_state, set_user_state

router = Router()

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    # Импортируем функцию start_handler динамически, чтобы избежать циклического импорта
    from handlers.start import start_handler
    await start_handler(message)