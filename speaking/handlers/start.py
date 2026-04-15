from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

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


@router.message(commands=["start"])
async def start_handler(message: Message):
    await message.answer(
        "Hello! 👋 Я твой персональный учитель английского 🇬🇧\n\nВыбери режим:",
        reply_markup=get_main_keyboard()
    )


# 👇 ВОТ ЭТО САМОЕ ВАЖНОЕ

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