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

last_bot_response = {}      # для голосовых сообщений
last_text_response = {}      # для текстовых сообщений

# ========== ПОЛНЫЙ СПИСОК КАТЕГОРИЙ И ТЕМ (40+ СЦЕНАРИЕВ) ==========
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
        {"name": "Собеседование на работу", "description": "Вы проходите собеседование на работу. Вам нужно представить свои навыки, опыт и мотивацию.", "goals": ["Опишите свой предыдущий опыт работы.", "Расскажите о навыках, подходящих для этой должности.", "Объясните, почему вы хотите получить эту работу."]},
        {"name": "Переговоры с клиентом", "description": "Вы участвуете в деловых переговорах с потенциальным клиентом.", "goals": ["Представьте свою компанию и предложение.", "Ответьте на возражения клиента.", "Договоритесь о выгодных условиях."]},
        {"name": "Презентация проекта", "description": "Вы проводите презентацию своего проекта перед руководством.", "goals": ["Кратко опишите суть проекта.", "Перечислите преимущества.", "Ответьте на вопросы слушателей."]},
        {"name": "Разговор с начальником", "description": "Вы обсуждаете с начальником свою работу, просите повышение или отпуск.", "goals": ["Чётко сформулируйте просьбу.", "Аргументируйте, почему вы её заслуживаете.", "Предложите компромисс."]},
        {"name": "Ежедневный планер", "description": "Вы обсуждаете с коллегой план задач на день.", "goals": ["Перечислите ключевые задачи.", "Уточните приоритеты.", "Согласуйте дедлайны."]},
        {"name": "Оценка производительности", "description": "У вас ежегодный обзор с руководителем.", "goals": ["Оцените свои достижения за год.", "Укажите зоны для роста.", "Поставьте цели на следующий период."]}
    ],
    "travel": [
        {"name": "Заказ такси в аэропорту", "description": "Вы звоните в службу такси, чтобы заказать машину до аэропорта.", "goals": ["Назовите точный адрес подачи.", "Укажите время и количество пассажиров.", "Уточните стоимость и способ оплаты."]},
        {"name": "Регистрация на рейс", "description": "Вы находитесь в аэропорту и проходите регистрацию на рейс.", "goals": ["Предъявите паспорт и билет.", "Сдайте багаж.", "Попросите место у окна."]},
        {"name": "Замена номера в отеле", "description": "Вам не подходит номер (шумно, не работает кондиционер).", "goals": ["Объясните причину недовольства.", "Попросите другой номер.", "Уточните возможность доплаты."]},
        {"name": "Покупка сувениров", "description": "Вы на рынке и хотите купить сувениры.", "goals": ["Спросите цену.", "Поторгуйтесь.", "Оплатите и попросите чек."]},
        {"name": "Спросить дорогу у местного", "description": "Вы заблудились в незнакомом городе.", "goals": ["Поздоровайтесь и извинитесь.", "Назовите пункт назначения.", "Уточните, как лучше дойти."]},
        {"name": "Бронирование отеля онлайн", "description": "Вы звоните в отель, чтобы забронировать номер.", "goals": ["Назовите даты и тип номера.", "Уточните цену и включён ли завтрак.", "Спросите про отмену бронирования."]},
        {"name": "Потеря багажа", "description": "Вы в аэропорту заявляете о потере багажа.", "goals": ["Опишите чемодан (цвет, размер).", "Сообщите номер рейса.", "Уточните, как отслеживать статус поиска."]}
    ],
    "daily": [
        {"name": "Заказ в ресторане", "description": "Вы в ресторане, делаете заказ.", "goals": ["Попросите меню.", "Сделайте заказ (учтите аллергии).", "Попросите счёт."]},
        {"name": "Визит к врачу", "description": "Вы на приёме у врача.", "goals": ["Опишите симптомы.", "Ответьте на вопросы.", "Уточните диагноз и лечение."]},
        {"name": "Звонок в техподдержку", "description": "У вас проблема с интернетом или компьютером.", "goals": ["Опишите проблему.", "Ответьте на вопросы оператора.", "Следуйте инструкциям."]},
        {"name": "Разговор с соседом", "description": "Вы встретили соседа в лифте или во дворе.", "goals": ["Поздоровайтесь и спросите, как дела.", "Поддержите беседу (погода, новости).", "Вежливо попрощайтесь."]},
        {"name": "Покупка продуктов в супермаркете", "description": "Вы в супермаркете, выбираете продукты.", "goals": ["Спросите, где нужный отдел.", "Уточните цену и срок годности.", "Оплатите на кассе."]},
        {"name": "Запись в спортзал", "description": "Вы звоните в фитнес-клуб, чтобы записаться.", "goals": ["Спросите про абонементы и цены.", "Уточните расписание групповых занятий.", "Запишитесь на пробную тренировку."]},
        {"name": "Ремонт техники", "description": "Вы сдаёте сломанный телефон в ремонт.", "goals": ["Опишите неисправность.", "Спросите стоимость диагностики и срок.", "Оставьте контактные данные."]}
    ],
    "hobby": [
        {"name": "Обсуждение любимой книги", "description": "Вы обсуждаете с другом любимую книгу.", "goals": ["Назовите книгу и автора.", "Расскажите, что понравилось.", "Спросите, что читает собеседник."]},
        {"name": "Спор о фильме", "description": "Вы спорите с другом о фильме.", "goals": ["Изложите сюжет.", "Назовите, что понравилось/не понравилось.", "Спросите мнение оппонента."]},
        {"name": "Планы на выходные", "description": "Вы обсуждаете с другом планы на выходные.", "goals": ["Предложите идеи.", "Обсудите время и место.", "Подтвердите договорённости."]},
        {"name": "Любимые рецепты", "description": "Вы делитесь любимым рецептом с другом.", "goals": ["Назовите блюдо и ингредиенты.", "Опишите процесс.", "Дайте совет."]},
        {"name": "Совет по видеоигре", "description": "Вы просите у друга совета по видеоигре.", "goals": ["Назовите игру и свой уровень.", "Спросите про сложные моменты.", "Попросите подсказку."]},
        {"name": "Обсуждение музыки", "description": "Вы обсуждаете любимую группу или концерт.", "goals": ["Назовите исполнителя.", "Расскажите, почему он вам нравится.", "Спросите, какую музыку слушает собеседник."]}
    ],
    "health": [
        {"name": "Запись к врачу по телефону", "description": "Вы звоните в поликлинику, чтобы записаться к врачу.", "goals": ["Назовите свои данные и полис.", "Опишите причину визита.", "Выберите время."]},
        {"name": "Разговор с фармацевтом в аптеке", "description": "Вы хотите купить лекарство.", "goals": ["Опишите симптомы.", "Спросите, какое лекарство подойдёт.", "Уточните дозировку и побочные эффекты."]},
        {"name": "Скорая помощь", "description": "Вы звоните в скорую помощь.", "goals": ["Чётко назовите адрес.", "Опишите, что случилось.", "Ответьте на вопросы диспетчера."]},
        {"name": "Разговор с психологом", "description": "Вы на сессии с психологом.", "goals": ["Расскажите, что вас беспокоит.", "Ответьте на уточняющие вопросы.", "Попросите совет."]}
    ],
    "family": [
        {"name": "Разговор с родителями", "description": "Вы звоните родителям, чтобы обсудить семейные дела.", "goals": ["Поздоровайтесь и спросите о здоровье.", "Расскажите о своих новостях.", "Попросите совета по семейному вопросу."]},
        {"name": "Планы с детьми", "description": "Вы обсуждаете с супругом/ой планы с детьми на выходные.", "goals": ["Предложите варианты.", "Согласуйте время и бюджет.", "Распределите обязанности."]},
        {"name": "Семейный ужин", "description": "Вы готовите ужин и обсуждаете его с членом семьи.", "goals": ["Спросите, что бы они хотели на ужин.", "Обсудите, кто что готовит.", "Договоритесь о времени."]},
        {"name": "Помощь с домашним заданием", "description": "Вы помогаете ребёнку с домашним заданием по английскому.", "goals": ["Объясните правило.", "Задайте наводящие вопросы.", "Похвалите за успехи."]}
    ],
    "tech": [
        {"name": "Настройка нового устройства", "description": "Вы звоните в поддержку, чтобы настроить новое устройство.", "goals": ["Назовите модель устройства.", "Опишите проблему при настройке.", "Следуйте инструкциям оператора."]},
        {"name": "Обсуждение софта с коллегой", "description": "Вы обсуждаете с коллегой преимущества разных программ.", "goals": ["Назовите программы.", "Сравните их функции.", "Придите к общему решению."]},
        {"name": "Заказ детали для компьютера", "description": "Вы звоните в магазин, чтобы заказать запчасть.", "goals": ["Назовите модель детали.", "Уточните наличие и цену.", "Оформите заказ."]},
        {"name": "Консультация по кибербезопасности", "description": "Вы консультируетесь со специалистом по защите данных.", "goals": ["Опишите, какую угрозу вы подозреваете.", "Спросите, как защитить свои данные.", "Запишите рекомендации."]}
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
    # Устанавливаем режим ролевой игры
    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": cat_id
    })
    await callback.answer(f"Выбрана тема: {topic}")
    # Клавиатура для ролевой игры
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

@dp.callback_query(lambda c: c.data == "custom_scenario")
async def custom_scenario_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "✍️ <b>Придумайте свой сценарий</b>\n\n"
        "Опишите ситуацию и роль бота одним сообщением.\n"
        "Пример:\n"
        "<i>Ты продавец в книжном магазине. Я покупатель, ищу книгу по фантастике. Ты предлагаешь новинки и помогаешь выбрать.</i>\n\n"
        "Напишите ваш сценарий:",
        parse_mode="HTML"
    )
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["awaiting_custom_scenario"] = True
    set_user_state(user_id, user_state)
    await callback.answer()

@dp.message(F.text)
async def process_custom_scenario(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if not user_state.get("awaiting_custom_scenario"):
        return
    user_state["awaiting_custom_scenario"] = False
    scenario_text = message.text
    topic = scenario_text[:50] + ("..." if len(scenario_text) > 50 else "")
    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": "custom",
        "custom_scenario": scenario_text
    })
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Завершить диалог")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"🎭 Ролевая игра: {topic}\n\n"
        f"<b>Ваш сценарий:</b> {scenario_text}\n\n"
        f"🗣️ Говорите голосом или пишите текстом.\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?».\n"
        f"Когда закончите, нажмите «📊 Завершить диалог» для анализа.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await message.answer("🎬 Можете начинать!", parse_mode="HTML")

# ---------- КНОПКИ РОЛЕВОЙ ИГРЫ ----------
@dp.message(F.text == "💡 Что ответить?")
async def hint_button(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    print(f"DEBUG: hint_button, mode={mode}")
    if mode != "roleplay_active":
        await message.answer("Эта кнопка доступна только в режиме ролевой игры.")
        return
    topic = user_state.get("roleplay_topic")
    history = user_state.get("history", [])
    if not topic:
        await message.answer("Сначала выберите тему ролевой игры через меню RolePlay.")
        return
    context = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-5:]])
    prompt = f"Ты – участник ролевой игры (тема: {topic}). Пользователь не знает, что ответить. Дай 2–3 коротких варианта ответа (по-английски). Контекст:\n{context}\nОтветь только вариантами."
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    hints = chat(prompt, max_tokens=200, temperature=0.7)
    await message.answer(f"💡 Варианты ответа:\n{hints}", parse_mode="HTML")

@dp.message(F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    print(f"DEBUG: finish_roleplay, mode={mode}")
    if mode != "roleplay_active":
        await message.answer("Эта кнопка доступна только в ролевой игре.")
        return
    history = user_state.get("history", [])
    if len(history) < 2:
        await message.answer("Диалог ещё не начался. Сначала отправьте несколько сообщений.")
        return
    conversation = "\n".join([f"{'User' if h['role']=='user' else 'Bot'}: {h['text']}" for h in history[-20:]])
    topic = user_state.get("roleplay_topic", "ролевая игра")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    prompt = (
        f"Ты опытный преподаватель английского. Дан диалог в ролевой игре на тему '{topic}'. "
        "Дай КОРОТКИЙ фидбек (не более 5 предложений) на русском языке. "
        "Используй HTML-теги: <b>жирный</b>, <i>курсив</i>, <blockquote>цитата</blockquote>. "
        "Добавь смайлики. Не пиши лишнего. Опиши главную ошибку и дай совет.\n\n"
        f"Диалог:\n{conversation}"
    )
    feedback = chat(prompt, max_tokens=400, temperature=0.5)
    if len(feedback) > 1000:
        feedback = feedback[:1000] + "..."
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

    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    await message.bot.send_chat_action(chat_id=message.chat.id, action="record_voice")
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

# ---------- КНОПКИ ПОД ГОЛОСОВЫМИ СООБЩЕНИЯМИ ----------
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
    data["translation"] = None
    last_bot_response[user_id] = data
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

# ---------- ТЕКСТОВЫЕ СООБЩЕНИЯ БОТА С КНОПКОЙ ПЕРЕВОДА ----------
async def send_text_with_translate_buttons(message: Message, text: str, user_id: int):
    """Отправляет текстовое сообщение с кнопкой "Перевести" (без кнопки "Скрыть")."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    sent = await message.answer(text, reply_markup=keyboard)
    last_text_response[user_id] = {
        "text": text,
        "translation": None,
        "message_id": sent.message_id
    }

# ---------- ОБРАБОТЧИКИ ДЛЯ ТЕКСТОВЫХ КНОПОК ПЕРЕВОДА ----------
@dp.callback_query(lambda c: c.data.startswith("translate_text_"))
async def translate_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет текста для перевода.", show_alert=True)
        return
    if data.get("translation"):
        translation = data["translation"]
    else:
        translation = chat(f"Переведи на русский: {data['text']}", max_tokens=300, temperature=0.3)
        data["translation"] = translation
        last_text_response[user_id] = data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 Оригинал", callback_data=f"original_text_{user_id}")]
    ])
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["message_id"],
        text=f"🇷🇺 {translation}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("original_text_"))
async def original_text_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    data = last_text_response.get(user_id)
    if not data or not data.get("text"):
        await callback.answer("Нет оригинала.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate_text_{user_id}")]
    ])
    await callback.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=data["message_id"],
        text=data["text"],
        reply_markup=keyboard
    )
    data["translation"] = None
    last_text_response[user_id] = data
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
    prompt = (
        "Ты опытный учитель английского. Дай КОРОТКИЙ фидбек (не более 5 предложений) на русском языке. "
        "Используй HTML-теги: <b>жирный</b>, <i>курсив</i>, <blockquote>цитата</blockquote>. "
        "Добавь смайлики. Не пиши лишних пояснений. Структура: сначала главная ошибка, потом что хорошо, потом совет.\n\n"
        f"Диалог:\n{conversation}"
    )
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    feedback = chat(prompt, max_tokens=400, temperature=0.5)
    if len(feedback) > 1000:
        feedback = feedback[:1000] + "..."
    await message.answer(f"📊 Ваш фидбек:\n\n{feedback}", parse_mode="HTML")

# ---------- КНОПКА ГЛАВНОЕ МЕНЮ ----------
@dp.message(F.text == "🏠 Главное меню")
async def main_menu_button(message: Message):
    user_id = message.from_user.id
    set_user_state(user_id, {"mode": None, "history": []})
    if user_id in last_bot_response:
        del last_bot_response[user_id]
    if user_id in last_text_response:
        del last_text_response[user_id]
    await message.answer("Режим завершён. Нажмите /start для выбора режима.", reply_markup=ReplyKeyboardRemove())

# ---------- ОБРАБОТКА ВСЕХ ОСТАЛЬНЫХ ТЕКСТОВЫХ СООБЩЕНИЙ ----------
@dp.message()
async def text_fallback(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    print(f"DEBUG: text_fallback, mode={mode}, text={message.text}")
    if mode in ("speaking_active", "roleplay_active"):
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        if mode == "roleplay_active":
            ai_response = await process_roleplay_message(user_id, message.text)
        else:
            ai_response = await process_voice_message(user_id, message.text)
        await send_text_with_translate_buttons(message, ai_response, user_id)
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