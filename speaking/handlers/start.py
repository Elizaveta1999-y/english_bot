from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from data.users import set_user_name, set_user_level, set_user_mode

router = Router()

# Клавиатура для выбора уровня
level_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="A1 (Начальный)"), KeyboardButton(text="A2 (Элементарный)")],
        [KeyboardButton(text="B1 (Средний)"), KeyboardButton(text="B2 (Выше среднего)")],
        [KeyboardButton(text="C1 (Продвинутый)")]
    ],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    # Спрашиваем имя
    await message.answer(
        "👋 Hello! I'm your AI English teacher.\nWhat is your name?",
        reply_markup=ReplyKeyboardRemove()
    )
    # Устанавливаем временное состояние "waiting_for_name"
    from data.users import users
    if user_id not in users:
        users[user_id] = {}
    users[user_id]["waiting_for_name"] = True

@router.message(F.text & (lambda m: m.from_user.id in data.users and data.users[m.from_user.id].get("waiting_for_name")))
async def get_name(message: Message):
    user_id = message.from_user.id
    name = message.text.strip()
    set_user_name(user_id, name)
    # Убираем флаг ожидания
    from data.users import users
    users[user_id]["waiting_for_name"] = False
    # Теперь спрашиваем уровень
    await message.answer(
        f"Nice to meet you, {name}! 🇬🇧\nChoose your English level:",
        reply_markup=level_keyboard
    )
    users[user_id]["waiting_for_level"] = True

@router.message(F.text & (lambda m: m.from_user.id in data.users and data.users[m.from_user.id].get("waiting_for_level")))
async def get_level(message: Message):
    user_id = message.from_user.id
    level_text = message.text
    # Преобразуем в код A1, B2 и т.д.
    level_map = {
        "A1 (Начальный)": "A1",
        "A2 (Элементарный)": "A2",
        "B1 (Средний)": "B1",
        "B2 (Выше среднего)": "B2",
        "C1 (Продвинутый)": "C1"
    }
    level = level_map.get(level_text, "B1")
    set_user_level(user_id, level)
    from data.users import users
    users[user_id]["waiting_for_level"] = False
    set_user_mode(user_id, "speaking")
    
    await message.answer(
        f"Perfect! Your level is {level}.\n\n🎤 Now you can send me voice messages, and I will correct your English.\n"
        f"Just speak something, and I'll reply with:\n"
        f"❌ Mistake → ✅ Correction → 📚 Explanation → ❓ Question\n\n"
        f"Let's start! Say something in English 🗣️",
        reply_markup=ReplyKeyboardRemove()
    )