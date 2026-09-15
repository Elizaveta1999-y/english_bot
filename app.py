import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from aiogram_ratelimiter import RateLimiter, Rate
from aiogram_ratelimiter.storages.redis import RedisStorage as RLRateStorage
from handlers import start, speaking, roleplay, common, voice, lessons, words, profile, support, listening, reading, writing, roleplay_voice
from handlers.subscription import router as subscription_router
from handlers.reading import router as reading_router
from handlers.grammar import router as grammar_router
from handlers.govorenie import router as govorenie_router
from handlers.agreement import router as agreement_router
from utils.db import init_db
from middleware.speaking_override import SpeakingOverrideMiddleware
from middleware.mode_transition import ModeTransitionMiddleware
from middleware.bot_active import BotActiveMiddleware

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
logging.getLogger("speaking.services.tts").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"

bot = Bot(token=BOT_TOKEN)

# ========== REDIS ==========
REDIS_URL = os.getenv("REDIS_URL")

if REDIS_URL:
    # FSM-состояния в Redis (чтобы не терять при рестарте и для мультиворкера в будущем)
    redis_client = Redis.from_url(REDIS_URL)
    storage = RedisStorage(redis=redis_client)
    logger.warning("Redis подключён: FSM в Redis, rate limiting включён")
else:
    storage = None
    redis_client = None
    logger.warning("REDIS_URL не задан: FSM в памяти, rate limiting ОТКЛЮЧЁН")

dp = Dispatcher(storage=storage) if storage else Dispatcher()

# ========== RATE LIMITING ==========
if redis_client is not None:
    try:
        rate_storage = RLRateStorage(redis=redis_client)
        rate_limiter = RateLimiter(
            storage=rate_storage,
            default_rate=Rate(30, 1),  # 30 событий в 1 секунду на пользователя
        )
        dp.message.middleware(rate_limiter)
        dp.callback_query.middleware(rate_limiter)
        logger.warning("Rate limiting: 30 событий/сек на пользователя")
    except Exception as e:
        logger.error(f"Не удалось включить rate limiting: {e}")

# ========== MIDDLEWARE ==========
dp.message.middleware(BotActiveMiddleware())
dp.callback_query.middleware(BotActiveMiddleware())

dp.callback_query.middleware(ModeTransitionMiddleware())

dp.message.middleware(SpeakingOverrideMiddleware())
dp.callback_query.middleware(SpeakingOverrideMiddleware())

# ========== ПОДКЛЮЧАЕМ РОУТЕРЫ ==========
dp.include_router(agreement_router)
dp.include_router(support.router)
dp.include_router(subscription_router)
dp.include_router(reading.router)
dp.include_router(speaking.router)
dp.include_router(roleplay.router)
dp.include_router(roleplay_voice.router)
dp.include_router(start.router)
dp.include_router(words.router)
dp.include_router(govorenie_router)
dp.include_router(writing.router)
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