# handlers/lessons.py
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, Message
from data.users import get_user_state, set_user_state
from data.lesson_data import LESSON_CONTENT
from services.deepseek import chat
from speaking.services.tts import text_to_voice

router = Router()

# ========== ТЕМАТИЧЕСКИЕ УРОКИ (список) ==========
THEMATIC_TOPICS = [
    "Present Simple vs Continuous",
    "Past Simple vs Present Perfect",
    "Модальные глаголы (can/could/must)",
    "Conditionals (0,1,2 типа)",
    "Пассивный залог",
    "Предлоги времени и места",
    "Фразовые глаголы (основные)",
    "Артикли a/an/the",
    "Степени сравнения прилагательных",
    "Косвенная речь",
    "Герундий и инфинитив",
    "Сложные союзы (although/despite)",
    "Лексика: путешествия",
    "Лексика: деловая переписка",
    "Лексика: семья и друзья",
    "Идиомы (10 популярных)",
    "Неправильные глаголы (тренажёр)",
    "Числительные и даты",
    "Вопросительные предложения (tag questions)",
    "Условные предложения 3 типа (wish/if only)"
]

# ========== УРОВНЕВЫЕ УРОКИ A1 ==========
LEVEL_A1_TOPICS = [
    "alphabet"   # ключ из LESSON_CONTENT
]

# Можно добавить отображаемые названия
LEVEL_A1_NAMES = {
    "alphabet": "🔤 Алфавит и произношение"
}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
user_page = {}

def get_thematic_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    start_idx = (page - 1) * 5
    end_idx = start_idx + 5
    page_topics = THEMATIC_TOPICS[start_idx:end_idx]
    buttons = []
    for idx, topic in enumerate(page_topics, start=start_idx):
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"thematic_{idx}")])
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀", callback_data="thematic_prev"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="thematic_none"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶", callback_data="thematic_next"))
    buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_lessons_keyboard(level: str) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру со списком уроков для уровня"""
    if level == "A1":
        topics = LEVEL_A1_TOPICS
        names = LEVEL_A1_NAMES
    else:
        # Для других уровней пока заглушка
        topics = []
        names = {}
    buttons = []
    for key in topics:
        display_name = names.get(key, key)
        buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"level_lesson_{level}_{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к уровням", callback_data="start_lessons")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def show_lesson_page(message: Message, user_id: int, edit: bool = True):
    """Отображает текущую страницу урока (из current_lesson)"""
    user_state = get_user_state(user_id)
    lesson = user_state.get("current_lesson")
    if not lesson:
        return
    key = lesson["key"]
    content = lesson["content"]
    page_idx = lesson.get("page", 0)
    pages = content["pages"]
    total_pages = len(pages)
    if page_idx >= total_pages:
        page_idx = total_pages - 1
    page = pages[page_idx]

    text = f"<b>📖 {lesson['topic']}</b>\n\n{page['text']}"

    nav_buttons = []
    if page_idx > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data="lesson_prev_page"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page_idx+1}/{total_pages}", callback_data="lesson_none"))
    if page_idx < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Далее ▶", callback_data="lesson_next_page"))

    lesson_buttons = [
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data=f"lesson_faq_{key}")],
        [InlineKeyboardButton(text="🤔 Задать вопрос", callback_data=f"lesson_ask_{key}")],
        [InlineKeyboardButton(text="📝 Начать практику", callback_data=f"lesson_practice_{key}")],
        [InlineKeyboardButton(text="🔙 Назад к списку уроков", callback_data=f"back_to_level_{lesson.get('level', 'A1')}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ]

    if page.get("has_audio_buttons"):
        letters = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']
        audio_rows = []
        for i in range(0, len(letters), 7):
            row = [InlineKeyboardButton(text=letter, callback_data=f"pronounce_{key}_{letter}") for letter in letters[i:i+7]]
            audio_rows.append(row)
        keyboard = InlineKeyboardMarkup(inline_keyboard=audio_rows + [nav_buttons] + lesson_buttons)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons] + lesson_buttons)

    if edit:
        if message.text == text and message.reply_markup == keyboard:
            return
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# ========== ГЛАВНОЕ МЕНЮ УРОКОВ ==========
@router.callback_query(lambda c: c.data == "start_lessons")
async def lessons_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if "lessons" not in user_state:
        user_state["lessons"] = {}
    set_user_state(user_id, user_state)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="A1 (Beginner)", callback_data="level_A1"),
         InlineKeyboardButton(text="A2 (Elementary)", callback_data="level_A2")],
        [InlineKeyboardButton(text="B1 (Intermediate)", callback_data="level_B1"),
         InlineKeyboardButton(text="B2 (Upper Intermediate)", callback_data="level_B2")],
        [InlineKeyboardButton(text="C1 (Advanced)", callback_data="level_C1")],
        [InlineKeyboardButton(text="📚 Тематические уроки", callback_data="thematic_menu")],
        [InlineKeyboardButton(text="📊 Моё обучение", callback_data="my_learning")],
        [InlineKeyboardButton(text="📝 Пройти тест (уровень)", callback_data="placement_test")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "📚 Режим уроков\n\n"
        "Выберите свой уровень, чтобы начать системное обучение.\n"
        "Или откройте «Тематические уроки» для быстрого разбора конкретных тем.\n"
        "«Моё обучение» — ваш прогресс и план на неделю.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ========== УРОВНЕВЫЕ УРОКИ ==========
@router.callback_query(lambda c: c.data.startswith("level_A") or c.data.startswith("level_B") or c.data.startswith("level_C"))
async def level_chosen(callback: CallbackQuery):
    level = callback.data.split("_")[1]  # A1, A2, ...
    if level == "A1":
        keyboard = get_level_lessons_keyboard("A1")
        await callback.message.edit_text(
            f"📖 Уровень {level} (Beginner)\n\nВыберите урок:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        # Заглушка для других уровней
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к выбору уровня", callback_data="start_lessons")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(
            f"📖 Уровень {level}\n\n🚧 Режим в разработке. Скоро здесь появятся уроки.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("level_lesson_"))
async def level_lesson_chosen(callback: CallbackQuery):
    parts = callback.data.split("_")
    level = parts[2]   # A1
    lesson_key = parts[3]  # alphabet
    content = LESSON_CONTENT.get(lesson_key)
    if not content:
        await callback.answer("Урок не найден", show_alert=True)
        return
    topic_name = LEVEL_A1_NAMES.get(lesson_key, lesson_key)
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["current_lesson"] = {
        "topic": topic_name,
        "key": lesson_key,
        "content": content,
        "page": 0,
        "level": level
    }
    set_user_state(user_id, user_state)
    await show_lesson_page(callback.message, user_id, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("back_to_level_"))
async def back_to_level(callback: CallbackQuery):
    level = callback.data.split("_")[3]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    # Очищаем текущий урок
    if "current_lesson" in user_state:
        del user_state["current_lesson"]
    set_user_state(user_id, user_state)
    # Показываем список уроков уровня
    if level == "A1":
        keyboard = get_level_lessons_keyboard("A1")
        await callback.message.edit_text(
            f"📖 Уровень {level} (Beginner)\n\nВыберите урок:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"📖 Уровень {level}\n\n🚧 Режим в разработке.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к уровням", callback_data="start_lessons")]
            ]),
            parse_mode="HTML"
        )
    await callback.answer()

# ========== ТЕМАТИЧЕСКИЕ УРОКИ (пагинация) ==========
@router.callback_query(lambda c: c.data == "thematic_menu")
async def thematic_lessons_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + 4) // 5
    user_page[user_id] = 1
    keyboard = get_thematic_keyboard(1, total_pages)
    if callback.message.text == "📚 Тематические уроки\n\nВыберите тему для изучения:" and callback.message.reply_markup == keyboard:
        await callback.answer("Вы уже в меню тем")
        return
    await callback.message.edit_text(
        "📚 Тематические уроки\n\nВыберите тему для изучения:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "thematic_next")
async def thematic_next_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + 4) // 5
    current = user_page.get(user_id, 1)
    if current < total_pages:
        user_page[user_id] = current + 1
        keyboard = get_thematic_keyboard(current + 1, total_pages)
        await callback.message.edit_text(
            "📚 Тематические уроки\n\nВыберите тему для изучения:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "thematic_prev")
async def thematic_prev_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + 4) // 5
    current = user_page.get(user_id, 1)
    if current > 1:
        user_page[user_id] = current - 1
        keyboard = get_thematic_keyboard(current - 1, total_pages)
        await callback.message.edit_text(
            "📚 Тематические уроки\n\nВыберите тему для изучения:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("thematic_") and c.data not in ("thematic_menu", "thematic_next", "thematic_prev", "thematic_none"))
async def show_thematic_lesson(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    topic_name = THEMATIC_TOPICS[idx]
    key = topic_name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("?", "")
    content = LESSON_CONTENT.get(key)
    if not content:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к темам", callback_data="thematic_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(
            f"📖 {topic_name}\n\n🚧 Урок в разработке. Скоро здесь будет теория.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
        return

    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["current_lesson"] = {
        "topic": topic_name,
        "key": key,
        "content": content,
        "page": 0,
        "source": "thematic"
    }
    set_user_state(user_id, user_state)
    await show_lesson_page(callback.message, user_id, edit=True)
    await callback.answer()

# ========== НАВИГАЦИЯ ПО СТРАНИЦАМ УРОКА ==========
@router.callback_query(lambda c: c.data == "lesson_next_page")
async def lesson_next_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lesson = user_state.get("current_lesson")
    if not lesson:
        await callback.answer("Урок не найден", show_alert=True)
        return
    pages = lesson["content"]["pages"]
    current = lesson.get("page", 0)
    if current + 1 < len(pages):
        lesson["page"] = current + 1
        set_user_state(user_id, user_state)
        await show_lesson_page(callback.message, user_id, edit=True)
    else:
        await callback.answer("Это последняя страница", show_alert=True)
    await callback.answer()

@router.callback_query(lambda c: c.data == "lesson_prev_page")
async def lesson_prev_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lesson = user_state.get("current_lesson")
    if not lesson:
        await callback.answer("Урок не найден", show_alert=True)
        return
    current = lesson.get("page", 0)
    if current > 0:
        lesson["page"] = current - 1
        set_user_state(user_id, user_state)
        await show_lesson_page(callback.message, user_id, edit=True)
    else:
        await callback.answer("Это первая страница", show_alert=True)
    await callback.answer()

# ========== FAQ, ВОПРОСЫ, ПРАКТИКА (общие) ==========
@router.callback_query(lambda c: c.data.startswith("lesson_faq_"))
async def lesson_faq(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    content = LESSON_CONTENT.get(key)
    if not content or not content.get("faq"):
        await callback.answer("FAQ не найдены", show_alert=True)
        return
    faq_text = "<b>❓ Часто задаваемые вопросы:</b>\n\n"
    for i, item in enumerate(content["faq"], 1):
        faq_text += f"<b>{i}. {item['question']}</b>\n{item['answer']}\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к уроку", callback_data=f"back_to_lesson_{key}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(faq_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_ask_"))
async def lesson_ask_start(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["lesson_qa"] = {
        "active": True,
        "topic_key": key,
        "topic_title": LESSON_CONTENT.get(key, {}).get("title", "этой теме")
    }
    set_user_state(user_id, user_state)
    await callback.message.edit_text(
        "🤔 Задайте ваш вопрос по теме. Я постараюсь объяснить максимально просто, с примерами из жизни.\n\n"
        "Если вопрос не по теме, я мягко верну вас к материалу.\n\n"
        "Напишите свой вопрос текстом.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_practice_"))
async def lesson_practice(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    await callback.message.edit_text(
        "📝 Практика в разработке. Скоро здесь будут интерактивные задания.\n\n"
        "Пока вы можете вернуться к теории или задать вопрос.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к уроку", callback_data=f"back_to_lesson_{key}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("back_to_lesson_"))
async def back_to_lesson(callback: CallbackQuery):
    key = callback.data.split("_")[3]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if "current_lesson" not in user_state or user_state["current_lesson"].get("key") != key:
        # Пытаемся восстановить урок
        topic_name = None
        # сначала проверим в тематических
        for t in THEMATIC_TOPICS:
            if t.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("?", "") == key:
                topic_name = t
                break
        if not topic_name:
            # проверим в A1
            for k in LEVEL_A1_TOPICS:
                if k == key:
                    topic_name = LEVEL_A1_NAMES.get(k, k)
                    break
        if not topic_name:
            await callback.message.edit_text("Урок не найден")
            await callback.answer()
            return
        content = LESSON_CONTENT.get(key)
        user_state["current_lesson"] = {
            "topic": topic_name,
            "key": key,
            "content": content,
            "page": 0
        }
        set_user_state(user_id, user_state)
    await show_lesson_page(callback.message, user_id, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_understand_"))
async def lesson_understand(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    await callback.message.edit_text(
        "✨ Прекрасно! Тогда предлагаю попрактиковаться, чтобы закрепить материал.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Начать практику", callback_data=f"lesson_practice_{key}")],
            [InlineKeyboardButton(text="🔙 Назад к уроку", callback_data=f"back_to_lesson_{key}")]
        ]),
        parse_mode="HTML"
    )
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if "lesson_qa" in user_state:
        del user_state["lesson_qa"]
    set_user_state(user_id, user_state)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_reask_"))
async def lesson_reask(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["lesson_qa"] = {
        "active": True,
        "topic_key": key,
        "topic_title": LESSON_CONTENT.get(key, {}).get("title", "этой теме")
    }
    set_user_state(user_id, user_state)
    await callback.message.edit_text(
        "🤔 Попробуйте задать вопрос иначе, или уточните, что именно осталось непонятным.\n\nНапишите ваш вопрос:",
        parse_mode="HTML"
    )
    await callback.answer()

# ========== АУДИО ДЛЯ БУКВ (ElevenLabs + кэш) ==========
CACHE_DIR = "cached_audio/alphabet"
os.makedirs(CACHE_DIR, exist_ok=True)

LETTER_PRONUNCIATION = {
    'A': 'A — эй, как в слове Apple',
    'B': 'B — би, как в слове Boy',
    'C': 'C — си, как в слове Cat',
    'D': 'D — ди, как в слове Dog',
    'E': 'E — и, как в слове Egg',
    'F': 'F — эф, как в слове Fish',
    'G': 'G — джи, как в слове Girl',
    'H': 'H — эйч, как в слове Hat',
    'I': 'I — ай, как в слове Ice',
    'J': 'J — джей, как в слове Juice',
    'K': 'K — кей, как в слове Kite',
    'L': 'L — эл, как в слове Lion',
    'M': 'M — эм, как в слове Mother',
    'N': 'N — эн, как в слове Night',
    'O': 'O — оу, как в слове Orange',
    'P': 'P — пи, как в слове Pen',
    'Q': 'Q — кью, как в слове Queen',
    'R': 'R — ар, как в слове Red',
    'S': 'S — эс, как в слове Sun',
    'T': 'T — ти, как в слове Tea',
    'U': 'U — ю, как в слове Umbrella',
    'V': 'V — ви, как в слове Violin',
    'W': 'W — дабл-ю, как в слове Window',
    'X': 'X — экс, как в слове X-ray',
    'Y': 'Y — уай, как в слове Yellow',
    'Z': 'Z — зед, как в слове Zebra'
}

@router.callback_query(lambda c: c.data.startswith("pronounce_"))
async def pronounce_letter(callback: CallbackQuery):
    parts = callback.data.split("_")
    lesson_key = parts[1]
    letter = parts[2]

    cached_path = os.path.join(CACHE_DIR, f"{letter}.mp3")
    if os.path.exists(cached_path):
        voice = FSInputFile(cached_path)
        reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ещё раз", callback_data=f"pronounce_{lesson_key}_{letter}")],
            [InlineKeyboardButton(text="🔙 Назад к алфавиту", callback_data=f"back_to_alphabet_{lesson_key}")]
        ])
        await callback.message.answer_voice(voice, caption=f"🔊 {letter}", reply_markup=reply_keyboard)
        await callback.answer()
        return

    await callback.message.answer("🔊 Генерирую произношение... Подождите секунду.")
    text_to_speak = LETTER_PRONUNCIATION.get(letter, f"{letter}")
    audio_path = await text_to_voice(text_to_speak)

    if audio_path and os.path.exists(audio_path):
        import shutil
        shutil.copy(audio_path, cached_path)
        voice = FSInputFile(cached_path)
        reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ещё раз", callback_data=f"pronounce_{lesson_key}_{letter}")],
            [InlineKeyboardButton(text="🔙 Назад к алфавиту", callback_data=f"back_to_alphabet_{lesson_key}")]
        ])
        await callback.message.answer_voice(voice, caption=f"🔊 {letter}", reply_markup=reply_keyboard)
        os.unlink(audio_path)
    else:
        await callback.message.answer("❌ Не удалось сгенерировать произношение. Попробуйте позже.")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("back_to_alphabet_"))
async def back_to_alphabet(callback: CallbackQuery):
    lesson_key = callback.data.split("_")[3]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("current_lesson", {}).get("key") == lesson_key:
        lesson = user_state["current_lesson"]
        lesson["page"] = 0
        set_user_state(user_id, user_state)
        await show_lesson_page(callback.message, user_id, edit=True)
    else:
        await callback.message.answer("Урок не найден, вернитесь в меню тем.")
    await callback.answer()

# ========== МОЁ ОБУЧЕНИЕ, ТЕСТ, ПРОЧЕЕ ==========
@router.callback_query(lambda c: c.data == "my_learning")
async def my_learning_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lessons_data = user_state.get("lessons", {})
    level = lessons_data.get("level", "не выбран")
    completed_topics = lessons_data.get("completed_topics", [])
    total_correct = lessons_data.get("total_correct", 0)
    total_wrong = lessons_data.get("total_wrong", 0)

    progress_text = f"📊 Ваш прогресс\n\n🎯 Уровень: {level}\n✅ Выполнено тем: {len(completed_topics)}\n📈 Правильных ответов: {total_correct}\n❌ Ошибок: {total_wrong}\n"
    if total_correct + total_wrong > 0:
        percent = round(total_correct / (total_correct + total_wrong) * 100)
        progress_text += f"📊 Точность: {percent}%\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Продолжить обучение", callback_data="continue_learning")],
        [InlineKeyboardButton(text="📅 План недели", callback_data="weekly_plan")],
        [InlineKeyboardButton(text="🔄 Сменить уровень", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")]
    ])
    await callback.message.edit_text(progress_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "continue_learning")
async def continue_learning(callback: CallbackQuery):
    await callback.message.edit_text("🚧 Режим продолжения обучения в разработке.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="my_learning")]
    ]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "weekly_plan")
async def weekly_plan_menu(callback: CallbackQuery):
    await callback.message.edit_text("📅 План недели в разработке.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="my_learning")]
    ]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "placement_test")
async def placement_test(callback: CallbackQuery):
    await callback.message.edit_text("📝 Тест на определение уровня в разработке.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()