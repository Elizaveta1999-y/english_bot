# app.py
import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from handlers import start, speaking, roleplay, common, voice, lessons, words, profile, skills, support, listening, reading, writing  
from handlers.subscription import router as subscription_router   # <-- добавляем
from handlers import listening
from handlers.reading import router as reading_router
from middleware.access import AccessMiddleware
from handlers.grammar import router as grammar_router


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(writing.router)
dp.include_router(reading.router)   # <-- ПЕРВЫМ после start
dp.include_router(listening.router)
dp.include_router(grammar_router) 
dp.include_router(support.router)
dp.include_router(subscription_router)
dp.include_router(words.router)
dp.include_router(roleplay.router)
dp.include_router(voice.router)
dp.include_router(common.router)
dp.include_router(lessons.router)
dp.include_router(speaking.router)
dp.include_router(profile.router)
dp.include_router(skills.router) 

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="support", description="Обратная связь"),
        BotCommand(command="subscription", description="Моя подписка"),   # <-- добавляем
    ]
    await bot.set_my_commands(commands)
    logger.info("Commands set")

async def on_startup():
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set to {webhook_url}")
    await set_commands(bot)

dp.startup.register(on_startup)

app = web.Application()

async def health_check(request):
    return web.Response(text="OK", status=200)

app.router.add_get('/health', health_check)

webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET)
webhook_requests_handler.register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting server on port {port}")
    web.run_app(app, host='0.0.0.0', port=port)

