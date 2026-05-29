import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Update, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def start_handler(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")],
        [InlineKeyboardButton(text="🎭 RolePlay", callback_data="start_roleplay")]
    ])
    await message.answer("Привет! Нажми кнопку.", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking(callback: CallbackQuery):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Кнопка 1"), KeyboardButton(text="Кнопка 2")],
            [KeyboardButton(text="Фидбек"), KeyboardButton(text="Главное меню")]
        ],
        resize_keyboard=True
    )
    await callback.message.answer("Голосовой режим. Вот кнопки:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "start_roleplay")
async def start_roleplay(callback: CallbackQuery):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Что ответить?"), KeyboardButton(text="Завершить диалог")],
            [KeyboardButton(text="Главное меню")]
        ],
        resize_keyboard=True
    )
    await callback.message.answer("Ролевая игра. Вот кнопки:", reply_markup=keyboard)
    await callback.answer()

# Кнопки
@dp.message(F.text == "Кнопка 1")
async def button1(message: Message):
    await message.answer("Вы нажали Кнопку 1")

@dp.message(F.text == "Кнопка 2")
async def button2(message: Message):
    await message.answer("Вы нажали Кнопку 2")

@dp.message(F.text == "Фидбек")
async def feedback(message: Message):
    await message.answer("Это фидбек")

@dp.message(F.text == "Главное меню")
async def main_menu(message: Message):
    await start_handler(message)

@dp.message(F.text == "Что ответить?")
async def hint(message: Message):
    await message.answer("Подсказка: попробуйте ответить по-английски")

@dp.message(F.text == "Завершить диалог")
async def finish(message: Message):
    await message.answer("Диалог завершён. Нажмите /start для нового.")

@dp.message(F.text)
async def echo(message: Message):
    await message.answer(f"Вы написали: {message.text}")

# ---------- ВЕБХУК ----------
async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(text="Error", status=500)

async def health(request):
    return web.Response(text="Bot is running", status=200)

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)
app.router.add_get("/", health)

async def on_startup(app):
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set to {webhook_url}")

app.on_startup.append(on_startup)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    web.run_app(app, host='0.0.0.0', port=port)