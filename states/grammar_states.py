from aiogram.fsm.state import StatesGroup, State

class GrammarStates(StatesGroup):
    in_progress = State()          # режим ожидания кнопок
    waiting_for_text = State()     # режим ожидания текстового ввода