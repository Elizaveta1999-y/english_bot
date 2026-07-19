from aiogram.fsm.state import State, StatesGroup

class ReadingStates(StatesGroup):
    in_progress = State()          # всегда активно, когда пользователь в режиме чтения
    waiting_for_text = State()     # когда ожидаем текстовый ответ (fill_one, fill_multiple)