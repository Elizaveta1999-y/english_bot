# handlers/lessons.py
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, FSInputFile, Message
from data.users import get_user_state, set_user_state
from data.lesson_data import LESSON_CONTENT
from services.deepseek import chat

router = Router()

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

@router.callback_query(lambda c: c.data == "thematic_menu")
async def thematic_lessons_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + 4) // 5
    user_page[user_id] = 1
    keyboard = get_thematic_keyboard(1, total_pages)
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
            f"📖 {topic_name}\n\n🚧 Урок в разработке. Скоро здесь будет теория и изображения.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
        return

    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    # Сохраняем информацию об уроке и начинаем с первой страницы
    user_state["current_lesson"] = {
        "topic": topic_name,
        "key": key,
        "content": content,
        "page": 0  # индекс текущей страницы (0-based)
    }
    set_user_state(user_id, user_state)

    # Показываем первую страницу
    await show_lesson_page(callback.message, user_id, edit=True)
    await callback.answer()

async def show_lesson_page(message: Message, user_id: int, edit: bool = True):
    """Отображает текущую страницу урока (с изображением)"""
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

    # Формируем текст: заголовок + содержимое страницы
    text = f"<b>📖 {lesson['topic']}</b>\n\n{page['text']}"
    # Клавиатура с навигацией и дополнительными кнопками
    nav_buttons = []
    if page_idx > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data="lesson_prev_page"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page_idx+1}/{total_pages}", callback_data="lesson_none"))
    if page_idx < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Далее ▶", callback_data="lesson_next_page"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        nav_buttons,
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data=f"lesson_faq_{key}")],
        [InlineKeyboardButton(text="🤔 Задать вопрос", callback_data=f"lesson_ask_{key}")],
        [InlineKeyboardButton(text="📝 Начать практику", callback_data=f"lesson_practice_{key}")],
        [InlineKeyboardButton(text="🔙 Назад к темам", callback_data="thematic_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])

    if edit:
        # Если у страницы есть изображение, отправляем его вместе с текстом (фото+подпись)
        if page.get("image") and os.path.exists(os.path.join("static", "lessons", page["image"])):
            # Отправляем новое сообщение с фото, а предыдущее удаляем или редактируем?
            # Лучше редактировать текст, а фото отправлять отдельно? Но тогда фото останется.
            # Чтобы фото менялось, проще отправить новое сообщение с фото и удалить старое.
            # Однако для сохранения чистоты интерфейса используем edit + отдельное фото? Нет.
            # В Telegram нельзя редактировать сообщение, чтобы добавить фото.
            # Поэтому при переходе на новую страницу будем удалять старое сообщение и отправлять новое с фото.
            # Но проще: для страниц без фото – редактируем, для страниц с фото – отправляем новое.
            # Я предлагаю: всегда отправлять новое сообщение (с фото, если есть) и удалять предыдущее.
            await message.delete()
            if os.path.exists(os.path.join("static", "lessons", page["image"])):
                photo = FSInputFile(os.path.join("static", "lessons", page["image"]))
                await message.answer_photo(photo, caption=text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            # Редактируем текст
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        if page.get("image") and os.path.exists(os.path.join("static", "lessons", page["image"])):
            photo = FSInputFile(os.path.join("static", "lessons", page["image"]))
            await message.answer_photo(photo, caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

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
    # Восстанавливаем урок с сохранённой страницей
    if "current_lesson" not in user_state or user_state["current_lesson"].get("key") != key:
        # Если нет, создаём заново
        topic_name = next((t for t in THEMATIC_TOPICS if t.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("?", "") == key), None)
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

@router.callback_query(lambda c: c.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery):
    level_code = callback.data.split("_")[1]
    level_name = {"A1":"A1 (Beginner)","A2":"A2 (Elementary)","B1":"B1 (Intermediate)","B2":"B2 (Upper Intermediate)","C1":"C1 (Advanced)"}.get(level_code, level_code)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к выбору уровня", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        f"📖 Уровень {level_name}\n\n🚧 Режим в разработке.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

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