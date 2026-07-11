from aiogram import Router, F
from aiogram.types import Message
from data.users import set_user_state
from handlers.start import show_main_menu
from handlers.listening import ListeningState
from states.speaking_states import SpeakingStates
from aiogram.fsm.context import FSMContext

router = Router()

@router.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ListeningState.answering_task:
        return
    if current_state == SpeakingStates.waiting_for_voice:
        return

    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    await show_main_menu(message, edit=True)