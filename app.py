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
from handlers.agreement import router as agreement_router   # импорт
from utils.db import init_db
from middleware.speaking_override import SpeakingOverrideMiddleware

logging.basicConfig(
    level=logging.INFO,   # Временно повысим до INFO, чтобы видеть все логи
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

# ========== ТОЛЬКО НАШ МИДЛВАР ==========
dp.message.middleware(SpeakingOverrideMiddleware())
dp.callback_query.middleware(SpeakingOverrideMiddleware())
logger.info("✅ SpeakingOverrideMiddleware зарегистрирован (единственный)")

# ========== ПОДКЛЮЧАЕМ РОУТЕРЫ ==========
# ПЕРВЫМ СТАВИМ agreement, чтобы он перехватывал команду до всех остальных
dp.include_router(agreement_router)
logger.info("✅ agreement_router подключён первым")

dp.include_router(start.router)
dp.include_router(speaking.router)
dp.include_router(roleplay.router)
dp.include_router(roleplay_voice.router)
dp.include_router(words.router)
dp.include_router(govorenie_router)
dp.include_router(writing.router)
dp.include_router(reading.router)
dp.include_router(listening.router)
dp.include_router(grammar_router)
dp.include_router(support.router)
dp.include_router(subscription_router)
dp.include_router(voice.router)
dp.include_router(common.router)
dp.include_router(lessons.router)
dp.include_router(profile.router)

# ========== КОМАНДЫ И ЗАПУСК ==========
async def set_commands(bot: Bot):
    # Удаляем старые команды, чтобы точно обновить
    await bot.delete_my_commands()
    logger.info("Старые команды удалены")
    
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="support", description="Обратная связь"),
        BotCommand(command="subscription", description="Моя подписка"),
        BotCommand(command="agreement", description="Пользовательское соглашение"),
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Команды установлены")

async def on_startup():
    logger.info("🚀 Запуск on_startup")
    await init_db()
    logger.info("База данных инициализирована")
    
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    logger.info(f"Вебхук установлен на {webhook_url}")
    
    webhook_info = await bot.get_webhook_info()
    logger.info(f"Инфо о вебхуке: {webhook_info}")
    
    await set_commands(bot)
    logger.info("✅ on_startup завершён")

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
    logger.info(f"Запуск сервера на порту {port}")
    web.run_app(app, host='0.0.0.0', port=port)