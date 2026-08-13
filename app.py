import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from handlers import start, speaking, roleplay, common, voice, lessons, words, profile, support, listening, reading, writing, roleplay_voice
from handlers.subscription import router as subscription_router
from handlers import listening
from handlers.reading import router as reading_router
from middleware.access import AccessMiddleware
from handlers.grammar import router as grammar_router
from utils.db import init_db, get_bot_active, is_user_blocked
from middleware.isolation import ModeIsolationMiddleware
from handlers.govorenie import router as govorenie_router
import traceback

# Импорт глобального middleware из handlers.speaking
from handlers.speaking import close_speaking_on_exit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --------------------- Логирование всех обновлений ---------------------
@dp.update.middleware()
async def log_update(handler, event, data):
    logger.info(f"📨 Received update: {event}")
    return await handler(event, data)

# --------------------- Глобальный обработчик ошибок (УНИВЕРСАЛЬНЫЙ) ---------------------
@dp.errors()
async def handle_errors(*args, **kwargs):
    event = None
    exception = None
    if args:
        if len(args) >= 1:
            event = args[0]
        if len(args) >= 2:
            exception = args[1]
    if 'event' in kwargs:
        event = kwargs['event']
    if 'exception' in kwargs:
        exception = kwargs['exception']
    
    if not event and args:
        event = args[0]
    if not exception and len(args) > 1:
        exception = args[1]
    
    error_text = ''.join(traceback.format_exception(None, exception, exception.__traceback__)) if exception else "Неизвестная ошибка"
    user_id = None
    if event:
        if hasattr(event, 'message') and event.message:
            user_id = event.message.from_user.id
        elif hasattr(event, 'callback_query') and event.callback_query:
            user_id = event.callback_query.from_user.id
        elif hasattr(event, 'from_user'):
            user_id = event.from_user.id
    logger.error(f"❌ Ошибка у пользователя {user_id}: {error_text}")
    if ADMIN_ID and exception:
        try:
            await bot.send_message(ADMIN_ID, f"⚠️ Ошибка в боте!\nПользователь: {user_id}\n\n{error_text[:500]}")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу: {e}")

# --------------------- Подключение роутеров (исправленный порядок) ---------------------
dp.include_router(start.router)          # 1. start (команды /start)
dp.include_router(speaking.router)       # 2. speaking
dp.include_router(roleplay.router)       # 3. roleplay – теперь ДО support и subscription
dp.include_router(roleplay_voice.router) # 4. голосовые для ролплей
dp.include_router(words.router)
dp.include_router(govorenie_router)
dp.include_router(writing.router)
dp.include_router(reading.router)
dp.include_router(listening.router)
dp.include_router(grammar_router)
dp.include_router(support.router)        # теперь ПОСЛЕ roleplay
dp.include_router(subscription_router)   # теперь ПОСЛЕ roleplay
dp.include_router(voice.router)
dp.include_router(common.router)
dp.include_router(lessons.router)
dp.include_router(profile.router)
# --------------------- Глобальный middleware для закрытия Speaking ---------------------
dp.message.middleware(close_speaking_on_exit)
dp.callback_query.middleware(close_speaking_on_exit)

# --------------------- Middleware изоляции режимов ---------------------
dp.message.middleware(ModeIsolationMiddleware())

# --------------------- Middleware для проверки статуса бота и блокировок ---------------------
@dp.message.middleware()
@dp.callback_query.middleware()
async def check_bot_status(handler, event, data):
    user_id = None
    if hasattr(event, 'from_user'):
        user_id = event.from_user.id
    elif hasattr(event, 'message') and event.message:
        user_id = event.message.from_user.id
    elif hasattr(event, 'callback_query') and event.callback_query:
        user_id = event.callback_query.from_user.id
    
    if user_id:
        if not await get_bot_active():
            await event.answer("🤖 Друзья! Бот решил немного передохнуть и отправился на техническое обслуживание.\nСкоро все наладим и вернём бота в строй так быстро, как только сможем.\nРекомендуем самостоятельно проверять статус через некоторое время.", show_alert=True if hasattr(event, 'answer') else False)
            return
        if await is_user_blocked(user_id):
            await event.answer("Ваш доступ ограничен.", show_alert=True if hasattr(event, 'answer') else False)
            return
    return await handler(event, data)

# --------------------- Команды и запуск ---------------------
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="support", description="Обратная связь"),
        BotCommand(command="subscription", description="Моя подписка"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Commands set")

async def on_startup():
    await init_db()
    logger.info("Database initialized")
    
    external_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not external_url:
        external_url = "https://english-bot-of29.onrender.com"
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set to {webhook_url}")
    
    webhook_info = await bot.get_webhook_info()
    logger.info(f"Webhook info: {webhook_info}")
    
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