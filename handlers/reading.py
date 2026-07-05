import logging
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from data.reading_loader import get_task
from utils.redis_utils import (
    get_global_welcome_index,
    get_user_progress,
    set_user_progress,
    get_user_stats,
    update_user_stats
)
from states.reading_states import ReadingStates

logger = logging.getLogger(__name__)
router = Router()

# -------------------- Приветственные сообщения --------------------
READING_WELCOME_MESSAGES = [
    "<b>Чтение</b>\n\n<i>Чтение — это ключ к расширению словарного запаса и пониманию структур языка. Регулярно читайте тексты разного уровня и учитесь выделять главное.</i>\n\nВыберите тип задания и уровень — и тренируйтесь в удобном темпе.",
    "<b>Чтение</b>\n\n<i>Умение быстро читать и понимать текст пригодится в любом контексте: от экзаменов до работы. Начните с коротких текстов и постепенно увеличивайте сложность.</i>\n\nГотовы попробовать?",
    "<b>Чтение</b>\n\n<i>Чтение на английском — это не только полезно, но и увлекательно. Выбирайте задания, которые вам интересны, и прокачивайте навык.</i>\n\nКакой тип выберете сегодня?",
    "<b>Чтение</b>\n\n<i>Навык чтения включает в себя понимание деталей, поиск информации и интерпретацию текста. Тренируйте все аспекты с нашими заданиями.</i>\n\nПриступим?",
    "<b>Чтение</b>\n\n<i>Читайте, анализируйте, отвечайте на вопросы — и вы заметите, как тексты становятся понятнее с каждым разом.</i>\n\nВыберите задание и уровень."
]

# -------------------- Маппинг типов и уровней --------------------
# Короткий ключ -> отображаемое имя (для кнопок)
TYPE_DISPLAY = {
    "podbor": "🥈 Подбор заголовка",
    "truefalse": "⚖️ True/False/Not stated",
    "choice": "☑️ Вопросы с выбором ответа",
    "fill": "🔄 Заполнение пропусков",
    "match": "🟰 Соотношение слова с определением",
    "order": "📄 Восстановление порядка абзацев",
    "random": "🎲 Случайный тип"
}

# Короткий -> полный русский ключ для JSON
TYPE_MAP = {
    "podbor": "Подбор_заголовка",
    "truefalse": "True_False_Not_stated",
    "choice": "Вопросы_с_выбором_ответа",
    "fill": "Заполнение_пропусков",
    "match": "Соотношение_слова_с_определением",
    "order": "Восстановление_порядка_абзацев"
}

# Короткий -> полный русский уровень для JSON
LEVEL_MAP = {
    "beginner": "Новичок",
    "intermediate": "Любитель",
    "expert": "Эксперт"
}

# Для отображения в прогресс-сообщении (можно взять из TYPE_DISPLAY)
DISPLAY_NAMES = {
    "Подбор_заголовка": "🥈 Подбор заголовка",
    "True_False_Not_stated": "⚖️ True/False/Not stated",
    "Вопросы_с_выбором_ответа": "☑️ Вопросы с выбором ответа",
    "Заполнение_пропусков": "🔄 Заполнение пропусков",
    "Соотношение_слова_с_определением": "🟰 Соотношение слова с определением",
    "Восстановление_порядка_абзацев": "📄 Восстановление порядка абзацев"
}

# -------------------- Клавиатуры --------------------
def get_type_choice_keyboard():
    buttons = []
    for key, label in TYPE_DISPLAY.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"reading_type:{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_keyboard(short_type: str):
    # Смайлики как на скриншоте: 🌱 Новичок, 🔥 Любитель, ⚡ Эксперт
    buttons = [
        [InlineKeyboardButton(text="🌱 Новичок", callback_data=f"reading_level:{short_type}:beginner")],
        [InlineKeyboardButton(text="🔥 Любитель", callback_data=f"reading_level:{short_type}:intermediate")],
        [InlineKeyboardButton(text="⚡ Эксперт", callback_data=f"reading_level:{short_type}:expert")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_types")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_action_keyboard(short_type: str, short_level: str, index: int):
    """Кнопки 'Показать ответ' и 'Завершить' в одной строке (без смайликов)."""
    buttons = [
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"reading_show_answer:{short_type}:{short_level}:{index}"),
            InlineKeyboardButton(text="Завершить", callback_data="reading_finish_session")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# -------------------- Формирование сообщения с заданием --------------------
async def render_task_message(user_id: int, short_type: str, short_level: str, index: int, paragraph_idx: int = 0):
    """
    Возвращает (текст, клавиатура) для полного сообщения.
    Все callback_data используют короткие ключи (short_type, short_level).
    """
    # Получаем полные русские ключи для JSON
    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)

    task = get_task(type_json, level_json, index)
    if not task:
        return None, None

    # Статистика
    correct, wrong = await get_user_stats(user_id, type_json, level_json)

    # Заголовок и прогресс
    display_name = TYPE_DISPLAY.get(short_type, short_type)
    text = f"<b>Режим: {display_name}</b>\n\n"
    text += "Внимательно прочитайте текст и выполните задание.\n\n"
    text += f"Ваш прогресс:\n"
    text += f"✔️ Правильно: {correct}\n"
    text += f"✖️ Ошибок: {wrong}\n\n"
    text += "/revision_mode — работа над ошибками\n"
    text += "/reset_progress — сбросить прогресс\n\n"

    # Тело задания (абзацы, вопрос)
    paragraphs = task.get("paragraphs", [])
    if not paragraphs or paragraph_idx >= len(paragraphs):
        paragraph_idx = 0
    current_paragraph = paragraphs[paragraph_idx]

    text += f"<i>{current_paragraph}</i>\n\n"
    text += f"<b>{task.get('question', '')}</b>\n\n"

    if task.get("input_type") == "text":
        text += "Введите ответ в чат.\n"

    # Клавиатура
    if task.get("input_type") == "text":
        keyboard = get_action_keyboard(short_type, short_level, index)
    else:
        options = task.get("options", [])
        kb_buttons = []
        for i, opt in enumerate(options):
            kb_buttons.append([InlineKeyboardButton(text=opt, callback_data=f"reading_answer:{short_type}:{short_level}:{index}:{i}")])
        # Строка действий
        kb_buttons.append([
            InlineKeyboardButton(text="Показать ответ", callback_data=f"reading_show_answer:{short_type}:{short_level}:{index}"),
            InlineKeyboardButton(text="Завершить", callback_data="reading_finish_session")
        ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    # Навигация по абзацам
    if len(paragraphs) > 1:
        nav_buttons = []
        if paragraph_idx > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀", callback_data=f"reading_prev_para:{short_type}:{short_level}:{index}:{paragraph_idx}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{paragraph_idx+1}/{len(paragraphs)}", callback_data="ignore"))
        if paragraph_idx < len(paragraphs) - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶", callback_data=f"reading_next_para:{short_type}:{short_level}:{index}:{paragraph_idx}"))
        new_kb = [nav_buttons] + keyboard.inline_keyboard
        keyboard = InlineKeyboardMarkup(inline_keyboard=new_kb)

    return text, keyboard

# -------------------- Обработчики --------------------
@router.callback_query(F.data == "start_reading")
async def start_reading(callback: CallbackQuery):
    global_idx = await get_global_welcome_index()
    welcome_text = READING_WELCOME_MESSAGES[global_idx]
    await callback.message.edit_text(welcome_text, reply_markup=get_type_choice_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "reading_back_to_main")
async def back_to_main(callback: CallbackQuery):
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("reading_type:"))
async def choose_type(callback: CallbackQuery):
    short_type = callback.data.split(":", 1)[1]
    if short_type == "random":
        all_types = ["podbor", "truefalse", "choice", "fill", "match", "order"]
        short_type = random.choice(all_types)
    await callback.message.edit_text(
        f"Выбран тип: {TYPE_DISPLAY.get(short_type, short_type)}\nВыберите уровень:",
        reply_markup=get_level_keyboard(short_type),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "reading_back_to_types")
async def back_to_types(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите тип задания:",
        reply_markup=get_type_choice_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("reading_level:"))
async def choose_level(callback: CallbackQuery, state: FSMContext):
    _, short_type, short_level = callback.data.split(":")
    user_id = callback.from_user.id

    # Получаем полные русские ключи
    type_json = TYPE_MAP.get(short_type, short_type)
    level_json = LEVEL_MAP.get(short_level, short_level)

    # Получаем прогресс
    index = await get_user_progress(user_id, type_json, level_json)
    task = get_task(type_json, level_json, index)
    if not task:
        index = 0
        await set_user_progress(user_id, type_json, level_json, index)
        task = get_task(type_json, level_json, index)
        if not task:
            await callback.message.edit_text("Задания для этого уровня пока отсутствуют. Попробуйте другой уровень.")
            await callback.answer()
            return

    # Сохраняем в FSM короткие ключи (для callback_data) и полные для задания
    await state.update_data(
        short_type=short_type,
        short_level=short_level,
        type_json=type_json,
        level_json=level_json,
        index=index,
        paragraph_idx=0
    )

    # Генерируем полное сообщение
    text, keyboard = await render_task_message(user_id, short_type, short_level, index, paragraph_idx=0)
    if text is None:
        await callback.message.edit_text("Ошибка загрузки задания.")
        await callback.answer()
        return

    # Устанавливаем FSM состояние
    if task.get("input_type") == "text":
        await state.set_state(ReadingStates.waiting_for_text)
    else:
        await state.set_state(None)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reading_next_para:"))
async def next_paragraph(callback: CallbackQuery, state: FSMContext):
    _, short_type, short_level, index_str, curr_para_str = callback.data.split(":")
    index = int(index_str)
    curr_para = int(curr_para_str)
    user_id = callback.from_user.id

    # Получаем полные ключи из состояния
    data = await state.get_data()
    type_json = data.get("type_json")
    level_json = data.get("level_json")
    if not type_json or not level_json:
        await callback.answer("Ошибка состояния")
        return

    task = get_task(type_json, level_json, index)
    if not task:
        await callback.answer("Ошибка задания")
        return

    paragraphs = task.get("paragraphs", [])
    if curr_para + 1 < len(paragraphs):
        new_para = curr_para + 1
        await state.update_data(paragraph_idx=new_para)
        text, keyboard = await render_task_message(user_id, short_type, short_level, index, new_para)
        if text:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reading_prev_para:"))
async def prev_paragraph(callback: CallbackQuery, state: FSMContext):
    _, short_type, short_level, index_str, curr_para_str = callback.data.split(":")
    index = int(index_str)
    curr_para = int(curr_para_str)
    user_id = callback.from_user.id

    data = await state.get_data()
    type_json = data.get("type_json")
    level_json = data.get("level_json")
    if not type_json or not level_json:
        await callback.answer("Ошибка состояния")
        return

    if curr_para > 0:
        new_para = curr_para - 1
        await state.update_data(paragraph_idx=new_para)
        text, keyboard = await render_task_message(user_id, short_type, short_level, index, new_para)
        if text:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reading_answer:"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    _, short_type, short_level, index_str, chosen_idx_str = callback.data.split(":")
    index = int(index_str)
    chosen_idx = int(chosen_idx_str)
    user_id = callback.from_user.id

    data = await state.get_data()
    type_json = data.get("type_json")
    level_json = data.get("level_json")
    if not type_json or not level_json:
        await callback.answer("Ошибка состояния")
        return

    task = get_task(type_json, level_json, index)
    if not task:
        await callback.answer("Задание не найдено")
        return

    correct = (chosen_idx == task["correct"])
    await update_user_stats(user_id, type_json, level_json, correct)

    if correct:
        await callback.answer("✅ Правильно!", show_alert=False)
    else:
        await callback.answer(
            f"❌ Неправильно. Правильный ответ: {task['options'][task['correct']]}",
            show_alert=False
        )

    # Переход к следующему заданию
    next_index = index + 1
    next_task = get_task(type_json, level_json, next_index)
    if not next_task:
        next_index = 0
        next_task = get_task(type_json, level_json, next_index)
        if not next_task:
            await callback.message.edit_text("Все задания пройдены! Начните заново или выберите другой уровень.")
            return

    await set_user_progress(user_id, type_json, level_json, next_index)
    await state.update_data(index=next_index, paragraph_idx=0)

    text, keyboard = await render_task_message(user_id, short_type, short_level, next_index, paragraph_idx=0)
    if text:
        if next_task.get("input_type") == "text":
            await state.set_state(ReadingStates.waiting_for_text)
        else:
            await state.set_state(None)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(ReadingStates.waiting_for_text)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    short_type = data.get("short_type")
    short_level = data.get("short_level")
    type_json = data.get("type_json")
    level_json = data.get("level_json")
    index = data.get("index")
    user_id = message.from_user.id

    if not all([type_json, level_json, index is not None]):
        await message.answer("Что-то пошло не так. Начните заново.")
        await state.clear()
        return

    task = get_task(type_json, level_json, index)
    if not task:
        await message.answer("Задание не найдено.")
        await state.clear()
        return

    correct_answer = task.get("correct")
    user_input = message.text.strip()

    if isinstance(correct_answer, list):
        user_parts = [p.strip().lower() for p in user_input.split(";") if p.strip()]
        correct_parts = [p.strip().lower() for p in correct_answer]
        correct = (user_parts == correct_parts)
    else:
        user_clean = "".join(user_input.split()).lower()
        correct_clean = "".join(str(correct_answer).split()).lower()
        correct = (user_clean == correct_clean)

    await update_user_stats(user_id, type_json, level_json, correct)

    if correct:
        await message.answer("✅ Правильно!")
    else:
        await message.answer(f"❌ Неправильно. Правильный ответ: {correct_answer}")

    # Переход к следующему заданию
    next_index = index + 1
    next_task = get_task(type_json, level_json, next_index)
    if not next_task:
        next_index = 0
        next_task = get_task(type_json, level_json, next_index)
        if not next_task:
            await message.answer("Все задания пройдены! Начните заново или выберите другой уровень.")
            await state.clear()
            return

    await set_user_progress(user_id, type_json, level_json, next_index)
    await state.update_data(index=next_index, paragraph_idx=0)

    text, keyboard = await render_task_message(user_id, short_type, short_level, next_index, paragraph_idx=0)
    if text:
        if next_task.get("input_type") == "text":
            await state.set_state(ReadingStates.waiting_for_text)
        else:
            await state.set_state(None)
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("reading_show_answer:"))
async def show_answer(callback: CallbackQuery):
    _, short_type, short_level, index_str = callback.data.split(":")
    index = int(index_str)
    # Получаем полные ключи из состояния
    data = await callback.state.get_data()
    type_json = data.get("type_json")
    level_json = data.get("level_json")
    if not type_json or not level_json:
        await callback.answer("Ошибка состояния")
        return
    task = get_task(type_json, level_json, index)
    if not task:
        await callback.answer("Задание не найдено")
        return

    correct = task.get("correct")
    explanation = task.get("explanation", "")
    await callback.answer(
        f"Правильный ответ: {correct}\n{explanation}",
        show_alert=True
    )

@router.callback_query(F.data == "reading_finish_session")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    type_json = data.get("type_json")
    level_json = data.get("level_json")
    user_id = callback.from_user.id

    if type_json and level_json:
        correct, wrong = await get_user_stats(user_id, type_json, level_json)
        total = correct + wrong
        if total == 0:
            text = "Сессия завершена!\nВы не ответили ни на одно задание."
        else:
            accuracy = (correct / total * 100)
            text = f"Сессия завершена!\n✅ Правильно: {correct}\n❌ Ошибок: {wrong}\n🎯 Точность: {accuracy:.1f}%"
    else:
        text = "Сессия завершена!"

    # Сразу показываем главное меню
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    # Можно также отправить отдельное сообщение со статистикой, но лучше заменить текущее
    # Но мы уже заменили на меню, поэтому статистика потеряется.
    # По вашему требованию: при нажатии "Завершить" выводится статистика и сразу главное меню.
    # Значит, сначала показываем статистику, потом через секунду меню? Или сразу меню + статистика в одном?
    # У вас сказано: "при нажатии завершить выводится статистика и НИКАКОЙ КНОПКИ В МЕНЮ А СРАЗУ ВЫВОДИТСЯ ГЛАВНОЕ МЕНЮ".
    # Это можно сделать так: отправить новое сообщение со статистикой, а затем вызвать show_main_menu для редактирования предыдущего?
    # Но мы редактируем текущее сообщение. Лучше показать статистику в этом же сообщении, а затем показать меню.
    # Так как мы редактируем, можно сначала отредактировать на статистику, а затем через 1-2 сек показать меню – но это неудобно.
    # Вариант: показываем статистику, а под ней кнопку "В меню" (которую вы не хотите). Но вы сказали "без кнопки, сразу главное меню".
    # Значит, после статистики мы должны перейти на главное меню. Можно сделать так: отредактировать сообщение на статистику, а затем сразу же вызвать show_main_menu для этого же сообщения (заменить текст и клавиатуру на меню).
    # В итоге пользователь увидит статистику, но она мгновенно сменится меню – это не очень хорошо.
    # Лучше показать статистику, а под ней кнопку "В меню", но вы сказали без кнопки.
    # Тогда можно отправить новое сообщение со статистикой, а предыдущее отредактировать на меню.
    # Но это сложно. Я предлагаю: при завершении сессии отправляем новое сообщение со статистикой, а предыдущее (с заданием) удаляем или редактируем на меню.
    # Однако проще: отредактировать текущее сообщение на статистику, и добавить кнопку "В меню" (это стандартно). Но вы настаиваете на "сразу главное меню".
    # Ок, тогда сделаем так: после получения статистики, мы вызываем show_main_menu для этого же сообщения (т.е. заменяем на главное меню). Статистика при этом будет потеряна.
    # Чтобы пользователь увидел статистику, можем отправить всплывающее уведомление (callback.answer) с краткой статистикой, а сообщение заменить на меню.
    # Так и сделаем.

    # Отправим всплывающее уведомление со статистикой
    await callback.answer(text, show_alert=True)
    # Затем показываем главное меню
    await show_main_menu(callback.message, edit=True)
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()