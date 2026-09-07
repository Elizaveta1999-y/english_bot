from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from data.users import get_user_state, set_user_state

router = Router()

@router.message(Command("agreement"))
async def agreement_command(message: Message, state: FSMContext):
    # --- ОЧИСТКА ЛЮБОГО АКТИВНОГО РЕЖИМА ---
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        user_state = get_user_state(message.from_user.id)
        user_state["mode"] = ""
        set_user_state(message.from_user.id, user_state)
        await message.answer("Практика завершена.", reply_markup=ReplyKeyboardRemove())

    # --- ОСНОВНАЯ ЛОГИКА ---
    text = (
        "<b>Пользовательское соглашение и другие документы</b>\n\n"
        "Все официальные документы доступны в одной папке:\n"
        "🔗 <a href='https://disk.yandex.ru/d/b0CooYtb5OxXgQ'>Открыть папку с документами</a>\n\n"
        "Ознакомьтесь с условиями использования, политикой конфиденциальности и тарифами."
    )
    await message.answer(text, parse_mode="HTML")