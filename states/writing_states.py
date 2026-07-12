from aiogram.fsm.state import State, StatesGroup

class WritingStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_answer = State()