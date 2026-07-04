from aiogram.fsm.state import State, StatesGroup

class ReadingStates(StatesGroup):
    waiting_for_text = State()