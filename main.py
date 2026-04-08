import asyncio
import aiohttp

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN
from services.openai import transcribe

from speaking.handler import start as speak_start, handle as speak_handle
from games.alias import start_alias, bot_explains, handle_user, alias_games
from games.wordsnake import start as ws_start, add_word, finish as ws_finish, games
from exam.exam import start as exam_start, send_task, check as exam_check, exam

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------- МЕНЮ ----------
def main_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [InlineKeyboardButton(text="📝 ОГЭ / ЕГЭ", callback_data="exam")],
        [InlineKeyboardButton(text="🎙 Speaking", callback_data="speak")]
    ])
    return kb


# ---------- СТАРТ ----------
@dp.message(Command("start"))
async def start(message: types.Message):
    text = """Hello! 👋 Я твой персональный учитель английского 🇬🇧

Я помогу тебе:
— прокачать разговорный английский
— подготовиться к экзаменам
— играть и учить слова

👇 Выбери режим:"""

    await message.answer(text, reply_markup=main_menu())


# ---------- КНОПКИ ----------
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):

    if call.data == "speak":
        await speak_start(call.message)

    elif call.data == "games":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Alias", callback_data="alias")],
            [InlineKeyboardButton(text="Wordsnake", callback_data="wordsnake")]
        ])
        await call.message.answer("Выбери игру:", reply_markup=kb)

    elif call.data == "alias":
        words = start_alias(call.from_user.id)

        text = "Слова:\n"
        for w, tr in words:
            text += f"{w} - {tr}\n"

        await call.message.answer(text)
        await bot_explains(bot, call.from_user.id)

    elif call.data == "wordsnake":
        base = ws_start(call.from_user.id)
        await call.message.answer(f"Слово: {base}")

    elif call.data == "exam":
        exam_start(call.from_user.id)
        await send_task(call.message)


# ---------- ГОЛОС ----------
@dp.message(F.voice)
async def voice(message: types.Message):
    file = await bot.get_file(message.voice.file_id)
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            audio = await r.read()

    text = transcribe(audio)

    user_id = message.from_user.id

    if user_id in alias_games:
        await handle_user(bot, message, text)
        return

    from data.users import speaking
    if user_id in speaking:
        await speak_handle(bot, message, text)
        return


# ---------- ТЕКСТ ----------
@dp.message()
async def text_handler(message: types.Message):
    user_id = message.from_user.id

    if user_id in games:
        await add_word(message)
        return

    if user_id in exam:
        await exam_check(message)
        return


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())