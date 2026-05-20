import os
import re
import asyncio
import logging
import subprocess
import tempfile
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Update, Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from speaking.services.stt import voice_to_text
from speaking.services.ai import process_voice_message, process_roleplay_message, generate_roleplay_feedback
from speaking.services.tts import text_to_voice
from data.users import set_user_state, get_user_state, set_user_name, set_user_mode, add_to_history, get_user_history
from services.deepseek import chat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def convert_to_opus(mp3_path: str) -> str:
    ogg_path = tempfile.mktemp(suffix=".ogg")
    cmd = [
        "ffmpeg", "-i", mp3_path,
        "-c:a", "libopus", "-ar", "16000", "-ac", "1",
        "-b:a", "16k", ogg_path, "-y"
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return ogg_path

last_bot_response = {}
last_text_response = {}

# ========== ДАННЫЕ ДЛЯ РОЛЕВОЙ ИГРЫ ==========
CATEGORIES = [
    ("🏢 Работа и бизнес", "work"),
    ("✈️ Путешествия", "travel"),
    ("🍽️ Повседневная жизнь", "daily"),
    ("📚 Развлечения и хобби", "hobby"),
    ("👨‍⚕️ Здоровье", "health"),
    ("🏠 Дом и семья", "family"),
    ("📱 Технологии", "tech")
]

TOPICS = {
    "work": [
        {"name": "Собеседование на работу", "description": "Вы проходите собеседование на работу.", "goals": ["Опишите опыт работы.", "Расскажите о навыках.", "Объясните, почему вы подходите."]},
        {"name": "Переговоры с клиентом", "description": "Деловые переговоры с клиентом.", "goals": ["Представьте предложение.", "Ответьте на возражения.", "Договоритесь об условиях."]},
        {"name": "Разговор с начальником", "description": "Обсуждаете с начальником повышение или отпуск.", "goals": ["Сформулируйте просьбу.", "Аргументируйте.", "Предложите компромисс."]}
    ],
    "travel": [
        {"name": "Заказ такси в аэропорту", "description": "Вы звоните в службу такси.", "goals": ["Назовите адрес.", "Укажите время.", "Уточните стоимость."]},
        {"name": "Регистрация на рейс", "description": "Вы в аэропорту, регистрируетесь на рейс.", "goals": ["Предъявите паспорт.", "Сдайте багаж.", "Попросите место у окна."]},
        {"name": "Покупка сувениров", "description": "Вы на рынке, покупаете сувениры.", "goals": ["Спросите цену.", "Поторгуйтесь.", "Оплатите."]}
    ],
    "daily": [
        {"name": "Заказ в ресторане", "description": "Вы в ресторане, делаете заказ.", "goals": ["Попросите меню.", "Сделайте заказ.", "Попросите счёт."]},
        {"name": "Визит к врачу", "description": "Вы на приёме у врача.", "goals": ["Опишите симптомы.", "Ответьте на вопросы.", "Уточните лечение."]},
        {"name": "Звонок в техподдержку", "description": "У вас проблема с интернетом.", "goals": ["Опишите проблему.", "Ответьте на вопросы.", "Следуйте инструкциям."]}
    ],
    "hobby": [
        {"name": "Обсуждение любимой книги", "description": "Обсуждаете с другом книгу.", "goals": ["Назовите книгу.", "Расскажите, что понравилось.", "Спросите мнение."]},
        {"name": "Планы на выходные", "description": "Договариваетесь о встрече.", "goals": ["Предложите идеи.", "Обсудите время.", "Подтвердите."]}
    ],
    "health": [
        {"name": "Запись к врачу по телефону", "description": "Звоните в поликлинику.", "goals": ["Назовите данные.", "Опишите симптомы.", "Выберите время."]},
        {"name": "Разговор с фармацевтом", "description": "В аптеке покупаете лекарство.", "goals": ["Опишите симптомы.", "Спросите о препарате.", "Уточните дозировку."]}
    ],
    "family": [
        {"name": "Разговор с родителями", "description": "Звоните родителям.", "goals": ["Поздоровайтесь.", "Расскажите новости.", "Спросите о здоровье."]},
        {"name": "Планы с детьми", "description": "Обсуждаете выходные с супругом.", "goals": ["Предложите варианты.", "Согласуйте время.", "Распределите обязанности."]}
    ],
    "tech": [
        {"name": "Настройка устройства", "description": "Звоните в поддержку.", "goals": ["Назовите модель.", "Опишите проблему.", "Следуйте инструкциям."]},
        {"name": "Обсуждение софта", "description": "С коллегой обсуждаете программы.", "goals": ["Назовите программы.", "Сравните функции.", "Выберите лучшую."]}
    ]
}

# ========== ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Speaking", callback_data="start_speaking")],
        [InlineKeyboardButton(text="🎭 RolePlay", callback_data="start_roleplay")]
    ])
    await message.answer(
        "Добро пожаловать в умный тренажер Английского языка! 🇺🇸\n\n"
        "Проходи уроки, выполняй задания и общайся голосом со своим персональным AI-тьютором! 🧠\n"
        "Выбирай режим и начни совершенствоваться в языке!\n\n"
        "🌟 Акция – полный доступ ко всему функционалу 700₽ 399₽/мес.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# ---------- SPEAKING ----------
@dp.callback_query(lambda c: c.data == "start_speaking")
async def start_speaking(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_state(user_id, {"mode": "speaking_active", "history": []})
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Я всё! Фидбек")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True
    )
    await callback.message.answer(
        "🎤 Голосовой режим активирован!\n\nГовори развёрнуто – так эффективнее для изучения! 🗣️",
        reply_markup=keyboard
    )
    await callback.answer()

# ---------- РОЛЕВАЯ ИГРА ----------
@dp.callback_query(lambda c: c.data == "start_roleplay")
async def start_roleplay(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.edit_text(
        "🎭 Выберите категорию или создайте свой сценарий.\n\nБот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cat_"))
async def show_topics(callback: CallbackQuery):
    cat_id = callback.data[4:]
    topics_list = TOPICS.get(cat_id, [])
    if not topics_list:
        await callback.answer("Нет тем в этой категории", show_alert=True)
        return
    buttons = []
    for idx, topic_info in enumerate(topics_list):
        buttons.append([InlineKeyboardButton(text=topic_info["name"], callback_data=f"topic_{cat_id}_{idx}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories")])
    topics_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    cat_display = next((c[0] for c in CATEGORIES if c[1] == cat_id), cat_id)
    await callback.message.edit_text(
        f"🎭 {cat_display}\n\nВыберите тему:",
        reply_markup=topics_keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Придумать свой сценарий", callback_data="custom_scenario")]
    ] + [[InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES])
    await callback.message.edit_text(
        "🎭 Выберите категорию или создайте свой сценарий.\n\nБот будет играть роль по сценарию. Вы можете говорить голосом или писать текстом.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("topic_"))
async def topic_chosen(callback: CallbackQuery):
    _, cat_id, idx_str = callback.data.split("_")
    idx = int(idx_str)
    topics_list = TOPICS.get(cat_id, [])
    if idx >= len(topics_list):
        await callback.answer("Тема не найдена", show_alert=True)
        return
    topic_info = topics_list[idx]
    topic = topic_info["name"]
    description = topic_info["description"]
    goals = topic_info["goals"]
    user_id = callback.from_user.id
    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": cat_id
    })
    await callback.answer(f"Выбрана тема: {topic}")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Завершить диалог")]
        ],
        resize_keyboard=True
    )
    goals_text = "\n".join([f"{i+1}) {goal}" for i, goal in enumerate(goals)])
    roleplay_info = (
        f"🎭 Ролевая игра: {topic}\n\n"
        f"📖 Ситуация: {description}\n\n"
        f"🎯 Ваши цели:\n{goals_text}\n\n"
        f"🗣️ Говорите голосом или пишите текстом.\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?».\n"
        f"Когда закончите, нажмите «📊 Завершить диалог» для анализа."
    )
    await callback.message.edit_text(roleplay_info, parse_mode="HTML")
    await callback.message.answer("🎬 Можете начинать!", reply_markup=keyboard)

# ---------- КНОПКИ РОЛЕВОЙ ИГРЫ (ЧТО ОТВЕТИТЬ? И ЗАВЕРШИТЬ) ----------
@dp.message(F.text == "💡 Что ответить?")
async def hint_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    topic = user_state.get("roleplay_topic")
    history = user_state.get("history", [])
    if not topic:
        await message.answer("Эта кнопка доступна только в режиме ролевой игры.")
        return
    context = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-5:]])
    prompt = f"Ты – участник ролевой игры (тема: {topic}). Пользователь не знает, что ответить. Дай 2–3 коротких варианта ответа (по-английски). Контекст:\n{context}\nОтветь только вариантами."
    hints = chat(prompt, max_tokens=200, temperature=0.7)
    await message.answer(f"💡 Варианты ответа:\n{hints}", parse_mode="HTML")

@dp.message(F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "roleplay_active":
        await message.answer("Эта кнопка доступна только в ролевой игре.")
        return
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("Диалог ещё не начался. Сначала отправьте несколько сообщений.")
        return
    conversation = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-20:]])
    topic = user_state.get("roleplay_topic", "ролевая игра")
    feedback = await generate_roleplay_feedback(conversation, topic)
    await message.answer(f"📊 Анализ диалога:\n\n{feedback}", parse_mode="HTML")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Продолжить диалог", callback_data="continue_roleplay")],
        [InlineKeyboardButton(text="🏠 Выйти в меню", callback_data="exit_to_menu")]
    ])
    await message.answer("Желаете продолжить ролевую игру или завершить?", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "continue_roleplay")
async def continue_roleplay(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Продолжаем. Отправляйте следующие сообщения.")

@dp.callback_query(lambda c: c.data == "exit_to_menu")
async def exit_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    await callback.message.answer("Режим завершён. Нажмите /start для выбора режима.", reply_markup=ReplyKeyboardRemove())
    await callback.answer()

# ---------- ОБРАБОТКА ГОЛОСОВЫХ СООБЩЕНИЙ ----------
@dp.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    file = await message.bot.get_file(message.voice.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    user_text = await voice_to_text(file_bytes.read())
    if not user_text:
        await message.answer("Не понял, повторите.")
        return

    mode = user_state.get("mode")
    if mode == "roleplay_active":
        ai_response = await process_roleplay_message(user_id, user_text)
    else:
        if mode != "speaking_active":
            set_user_mode(user_id, "speaking_active")
        ai_response = await process_voice_message(user_id, user_text)

    # история
    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    # ответ голосом
    voice_path = await text_to_voice(ai_response)
    if voice_path:
        ogg_path = convert_to_opus(voice_path)
        with open(ogg_path, 'rb') as f:
            audio_bytes = f.read()
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
        ])
        sent = await message.answer_audio(
            BufferedInputFile(audio_bytes, filename='voice.ogg'),
            caption="",
            reply_markup=inline_keyboard
        )
        last_bot_response[user_id] = {
            "text": ai_response,
            "translation": None,
            "audio_message_id": sent.message_id
        }
        os.unlink(voice_path)
        os.unlink(ogg_path)
    else:
        await message.answer(ai_response)

# ---------- КНОПКИ ПОД ГОЛОСОВЫМИ СООБЩЕНИЯМИ (ПЕРЕВОД И Т.Д.) ----------
@dp.callback_query(lambda c: c.data.startswith("show_text_"))
async def show_text(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста.", show_alert=True)
        return
    original = data["text"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
         InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"📝 {original}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("translate_") and not c.data.startswith("translate_text_"))
async def translate_caption(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста для перевода.", show_alert=True)
        return
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(f"Переведи на русский: {data['text']}", max_tokens=300, temperature=0.3)
        data["translation"] = translation
        last_bot_response[user_id] = data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_{user_id}"),
         InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("original_") and not c.data.startswith("original_text_"))
async def revert_to_original(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_{user_id}"),
         InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption=f"📝 {data['text']}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("hide_") and not c.data.startswith("hide_text_"))
async def hide_message(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = last_bot_response.get(user_id)
    if not data or not data.get("audio_message_id"):
        await callback.answer("Нет сообщения.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"show_text_{user_id}")]
    ])
    await callback.bot.edit_message_caption(
        chat_id=callback.message.chat.id,
        message_id=data["audio_message_id"],
        caption="",
        reply_markup=keyboard
    )
    data["translation"] = None
    last_bot_response[user_id] = data
    await callback.answer()

# ---------- КНОПКА ФИДБЕК ДЛЯ SPEAKING ----------
@dp.message(F.text == "📊 Я всё! Фидбек")
async def feedback_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "speaking_active":
        await message.answer("Фидбек доступен только в режиме Speaking.")
        return
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("Вы ещё не общались. Отправьте несколько голосовых сообщений.")
        return
    conversation = "\n".join([f"{'Student' if h['role']=='user' else 'Teacher'}: {h['text']}" for h in history[-10:]])
    prompt = f"Ты опытный учитель английского. Дай короткий фидбек на русском языке.\nДиалог:\n{conversation}\nФормат:\n<b>📝 Ошибки и исправления</b>\n<b>💡 Рекомендации</b>\n<b>📚 Словарик</b>"
    feedback = chat(prompt, max_tokens=600, temperature=0.5)
    await message.answer(f"📊 Ваш фидбек:\n\n{feedback}", parse_mode="HTML")

# ---------- КНОПКА ГЛАВНОЕ МЕНЮ (ОБЩАЯ) ----------
@dp.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    if user_id in last_bot_response:
        del last_bot_response[user_id]
    if user_id in last_text_response:
        del last_text_response[user_id]
    await message.answer("Режим завершён. Нажмите /start для выбора режима.", reply_markup=ReplyKeyboardRemove())

# ---------- ОБРАБОТКА ЛЮБЫХ ДРУГИХ ТЕКСТОВЫХ СООБЩЕНИЙ ----------
@dp.message()
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    if mode in ("speaking_active", "roleplay_active"):
        if mode == "roleplay_active":
            ai_response = await process_roleplay_message(user_id, message.text)
        else:
            ai_response = await process_voice_message(user_id, message.text)
        await message.answer(ai_response)
        # сохраняем историю
        history = user_state.get("history", [])
        history.append({"role": "user", "text": message.text})
        history.append({"role": "assistant", "text": ai_response})
        if len(history) > 20:
            history = history[-20:]
        user_state["history"] = history
        set_user_state(user_id, user_state)
    else:
        await message.answer("Нажмите /start и выберите Speaking или RolePlay.")

# ---------- ВЕБХУК ----------
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = "my-secret-key"

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
        external_url = "https://english-bot-of29.onrender.com"  # замените на ваш URL
    webhook_url = f"{external_url}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook set to {webhook_url}")

app.on_startup.append(on_startup)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    web.run_app(app, host='0.0.0.0', port=port)