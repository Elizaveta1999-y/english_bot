from aiogram.fsm.state import State, StatesGroup

class SpeakingStates(StatesGroup):
    waiting_for_voice = State()  # режим ожидания голосовых/текстовых сообщений