import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import BotCommand, TelegramObject
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from typing import Callable, Dict, Any, Awaitable
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


# ========== БОТ С ОЧЕРЕДЬЮ ОТПРАВКИ ==========
class RateLimitedBot(Bot):
    """
    Бот, который пропускает все исходящие запросы через глобальный лимит.
    Это предотвращает ошибки 429 от Telegram при массовой отправке.
    """

    # Лимит: 30 операций в секунду на весь бот
    MAX_PER_SECOND = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._send_lock = asyncio.Lock()
        self._last_send = 0.0
        self._min_interval = 1.0 / self.MAX_PER_SECOND

    async def _wait_turn(self):
        async with self._send_lock:
            now = asyncio.get_event_loop().time()
            delta = now - self._last_send
            if delta < self._min_interval:
                await asyncio.sleep(self._min_interval - delta)
            self._last_send = asyncio.get_event_loop().time()

    # Перехватываем все основные отправки
    async def send_message(self, *args, **kwargs):
        await self._wait_turn()
        return await super().send_message(*args, **kwargs)

    async def send_voice(self, *args, **kwargs):
        await self._wait_turn()
        return await super().send_voice(*args, **kwargs)

    async def send_photo(self, *args, **kwargs):
        await self._wait_turn()
        return await super().send_photo(*args, **kwargs)

    async def send_document(self, *args, **kwargs):
        await self._wait_turn()
        return await super().send_document(*args, **kwargs)

    async def send_audio(self, *args, **kwargs):
        await self._wait_turn()
        return await super().send_audio(*args, **kwargs)

    async def send_video(self, *args, **kwargs):
        await self._wait_turn()
        return await super().send_video(*args, **kwargs)

    async def send_animation(self, *args, **kwargs):
        await self._wait_turn()
        return await super().send_animation(*args, **kwargs)

    async def edit_message_text(self, *args, **kwargs):
        await self._wait_turn()
        return await super().edit_message_text(*args, **kwargs)

    async def edit_message_caption(self, *args, **kwargs):
        await self._wait_turn()
        return await super().edit_message_caption(*args, **kwargs)

    async def edit_message_reply_markup(self, *args, **kwargs):
        await self._wait_turn()
        return await super().edit_message_reply_markup(*args, **kwargs)


bot = RateLimitedBot(token=BOT_TOKEN)

# ========== REDIS ==========
REDIS_URL = os.getenv("REDIS_URL")

if REDIS_URL:
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    storage = RedisStorage.from_url(REDIS_URL)
    logger.warning("Redis подключён: FSM в Redis")
else:
    redis_client = None
    storage = None
    logger.warning("REDIS_URL не задан: FSM в памяти")


# ========== RATE LIMITER НА ВХОДЯЩИЕ ==========
class SimpleRateLimiter(BaseMiddleware):
    """
    Ограничивает количество апдейтов от одного пользователя.
    Защищает от спама от одного человека.
    """

    def __init__(self, redis_client: Redis, max_events: int = 30, window_seconds: int = 1):
        self.redis = redis_client
        self.max_events = max_events
        self.window = window_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        key = f"ratelimit:{user.id}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window)
            if count > self.max_events:
                logger.debug(f"Rate limit exceeded for user {user.id}")
                return
        except Exception as e:
            logger.warning(f"Rate limiter error: {e}")

        return await handler(event, data)


dp = Dispatcher(storage=storage) if storage else Dispatcher()

if redis_client is not None:
    rate_limiter = SimpleRateLimiter(redis_client, max_events=30, window_seconds=1)
    dp.message.middleware(rate_limiter)
    dp.callback_query.middleware(rate_limiter)
    logger.warning("Rate limiting на входящие: 30 событий/сек на пользователя")

# ========== MIDDLEWARE ==========
dp.message.middleware(BotActiveMiddleware())
dp.callback_query.middleware(BotActiveMiddleware())

dp.callback_query.middleware(ModeTransitionMiddleware())

dp.message.middleware(SpeakingOverrideMiddleware())
dp.callback_query.middleware(SpeakingOverrideMiddleware())

# ========== РОУТЕРЫ ==========
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