from aiogram import Router, F
from aiogram.types import Message
from data.users import set_user_state
from handlers.start import show_main_menu
from handlers.listening import ListeningState
from states.speaking_states import SpeakingStates
from aiogram.fsm.context import FSMContext

router = Router()

# ============ УДАЛЯЕМ ДУБЛИРУЮЩИЙ ХЕНДЛЕР ДЛЯ "🏠 Главное меню" ============
# Он перехватывал кнопку в режиме Speaking и мешал её работе.
# Весь функционал главного меню уже есть в speaking.py и start.py.

# ============ ОБЩИЙ ОБРАБОТЧИК (catch-all) С ПРОПУСКОМ КНОПОК ============
@router.message(F.text)
async def catch_all(message: Message, state: FSMContext):
    """
    Обрабатывает все текстовые сообщения, которые не были обработаны другими роутерами.
    Пропускает кнопки Speaking (чтобы они дошли до других хендлеров).
    """
    # Список текстов, которые должны быть обработаны другими роутерами (speaking, roleplay и т.д.)
    skip_texts = [
        "📊 Я всё! Фидбек",
        "🏠 Главное меню",
        "💡 Что ответить?",
        "📊 Завершить диалог",
        # Добавьте другие кнопки, если нужно
    ]
    
    if message.text in skip_texts:
        # Просто выходим, не отвечая, чтобы сообщение дошло до других хендлеров
        return

    # Если мы здесь, значит, сообщение не распознано – можно дать подсказку
    current_state = await state.get_state()
    if current_state == ListeningState.answering_task:
        # В режиме аудирования игнорируем текст
        return

    await message.answer("Извините, я не понял вашу команду. Пожалуйста, используйте кнопки меню или напишите /start.")