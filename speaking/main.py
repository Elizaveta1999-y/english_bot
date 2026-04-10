import threading
import os
from flask import Flask
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from handlers.start import start
from handlers.buttons import button_handler
from speaking.handler import handle_voice, start as speak_start

# ===== Flask сервер (чтобы Render не падал) =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ===== Telegram бот =====
def run_bot():
    import os
    TOKEN = os.getenv("TELEGRAM_TOKEN")

    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Бот запущен...")
    app_bot.run_polling()

# ===== Запуск =====
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    run_bot()