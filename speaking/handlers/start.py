from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

router = Router()


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Игры")],
            [KeyboardButton(text="📒 ОГЭ / ЕГЭ")],
            [KeyboardButton(text="🎤 Speaking")]
        ],
        resize_keyboard=True
    )


# ✅ ПРАВИЛЬНО ДЛЯ AIROGRAM 3
@router.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Hello! 👋 Я твой персональный учитель английского 🇬🇧\n\nВыбери режим:",
        reply_markup=get_main_keyboard()
    )


# обработка кнопок
@router.message()
async def handle_menu(message: Message):
    text = message.text

    if text == "🎤 Speaking":
        await message.answer("🎤 Say something in English!")

    elif text == "🎮 Игры":
        await message.answer("🎮 Режим игр скоро будет!")

    elif text == "📒 ОГЭ / ЕГЭ":
        await message.answer("📒 Режим экзамена скоро будет!")

    else:
        await message.answer("Я не понял, выбери кнопку 👇")