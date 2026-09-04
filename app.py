import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from handlers import start, speaking, roleplay, common, voice, lessons, words, profile, support, listening, reading, writing, roleplay_voice
from handlers.subscription import router as subscription_router
from handlers.reading import router as reading_router
from handlers.grammar import router as grammar_router
from handlers.govorenie import router as govorenie_router
from handlers.agreement import router as agreement_router
from utils.db import init_db
from middleware.speaking_override import SpeakingOverrideMiddleware

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== МИДЛВАР ==========
dp.message.middleware(SpeakingOverrideMiddleware())
dp.callback_query.middleware(SpeakingOverrideMiddleware())
logger.info("✅ SpeakingOverrideMiddleware зарегистрирован")

# ========== ПОДКЛЮЧАЕМ РОУТЕРЫ (ВАЖНЫЙ ПОРЯДОК!) ==========
# Сначала идут команды, которые НЕ должны перехватываться start-ом
dp.include_router(agreement_router)      # /agreement
dp.include_router(support.router)        # /support   ← перенесены выше start
dp.include_router(subscription_router)   # /subscription
# Теперь start, который может иметь общий обработчик, но он не перехватит support/subscription
dp.include_router(start.router)
# Остальные роутеры
dp.include_router(speaking.router)
dp.include_router(roleplay.router)
dp.include_router(roleplay_voice.router)
dp.include_router(words.router)
dp.include_router(govorenie_router)
dp.include_router(writing.router)
dp.include_router(reading.router)
dp.include_router(listening.router)
dp.include_router(grammar_router)
dp.include_router(voice.router)
dp.include_router(common.router)
dp.include_router(lessons.router)
dp.include_router(profile.router)

# ========== КОМАНДЫ МЕНЮ ==========
async def set_commands(bot: Bot):
    await bot.delete_my_commands()
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="support", description="Обратная связь"),
        BotCommand(command="subscription", description="Моя подписка"),
        BotCommand(command="agreement", description="Пользовательское соглашение"),
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Команды установлены")

async def on_startup():
    await init_db()
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    await set_commands(bot)

dp.startup.register(on_startup)

app = web.Application()
app.router.add_get('/health', lambda r: web.Response(text="OK"))

webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET)
webhook_requests_handler.register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    web.run_app(app, host='0.0.0.0', port=port)