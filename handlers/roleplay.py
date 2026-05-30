# Файл: english_bot/handlers/roleplay.py

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, # ... и так далее
from data.users import set_user_state, get_user_state
from services.deepseek import chat
from speaking.services.ai import is_safe_message, process_roleplay_message

# !!! ЭТА СТРОКА БЫЛА ПРОПУЩЕНА !!!
router = Router()

# ... ниже идут декораторы вида @router.message(F.text) и сами функции-обработчики