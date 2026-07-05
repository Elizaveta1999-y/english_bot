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
# Ключи для callback (сокращённые) -> отображаемое имя
TYPE_KEYS = {
    "podbor": "🥈 Подбор заголовка",
    "truefalse": "⚖️ True/False/Not stated",
    "choice": "☑️ Вопросы с выбором ответа",
    "fill": "🔄 Заполнение пропусков",
    "match": "🟰 Соотношение слова с определением",
    "order": "📄 Восстановление порядка абзацев",
    "random": "🎲 Случайный тип"
}

# Сокращённый ключ -> русский ключ для JSON
TYPE_MAP = {
    "podbor": "Подбор_заголовка",
    "truefalse": "True_False_Not_stated",
    "choice": "Вопросы_с_выбором_ответа",
    "fill": "Заполнение_пропусков",
    "match": "Соотношение_слова_с_определением",
    "order": "Восстановление_порядка_абзацев"
}

# Русский ключ -> отображаемое имя (для прогресса)
DISPLAY_NAMES = {
    "Подбор_заголовка": "🥈 Подбор заголовка",
    "True_False_Not_stated": "⚖️ True/False/Not stated",
    "Вопросы_с_выбором_ответа": "☑️ Вопросы с выбором ответа",
    "Заполнение_пропусков": "🔄 Заполнение пропусков",
    "Соотношение_слова_с_определением": "🟰 Соотношение слова с определением",
    "Восстановление_порядка_абзацев": "📄 Восстановление порядка абзацев"
}

# Уровни (сокращённый -> русский)
LEVEL_MAP = {
    "beginner": "Новичок",
    "intermediate": "Любитель",
    "expert": "Эксперт"
}

# -------------------- Клавиатуры --------------------
def get_type_choice_keyboard():
    buttons = []
    for key, label in TYPE_KEYS.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"reading_type:{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_keyboard(type_key: str):
    # Без смайликов, только текст
    buttons = [
        [InlineKeyboardButton(text="Новичок", callback_data=f"reading_level:{type_key}:beginner")],
        [InlineKeyboardButton(text="Любитель", callback_data=f"reading_level:{type_key}:intermediate")],
        [InlineKeyboardButton(text="Эксперт", callback_data=f"reading_level:{type_key}:expert")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_types")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_action_keyboard(type_key: str, level_key: str, index: int):
    """Кнопки 'Показать ответ' и 'Завершить' в одной строке."""
    buttons = [
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"reading_show_answer:{type_key}:{level_key}:{index}"),
            InlineKeyboardButton(text="Завершить", callback_data="reading_finish_session")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# -------------------- Формирование сообщения с заданием --------------------
async def render_task_message(user_id: int, type_key: str, level_key: str, index: int, paragraph_idx: int = 0):
    """
    Возвращает (текст, клавиатура) для полного сообщения:
    - Заголовок режима
    - Прогресс
    - Текст задания (абзац, вопрос, варианты/подсказка)
    - Кнопки навигации и действий
    """
    task = get_task(type_key, level_key, index)
    if not task:
        return None, None

    # Статистика
    correct, wrong = await get_user_stats(user_id, type_key, level_key)

    # Заголовок и прогресс
    display_name = DISPLAY_NAMES.get(type_key, type_key)
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
        keyboard = get_action_keyboard(type_key, level_key, index)
    else:
        options = task.get("options", [])
        kb_buttons = []
        for i, opt in enumerate(options):
            kb_buttons.append([InlineKeyboardButton(text=opt, callback_data=f"reading_answer:{type_key}:{level_key}:{index}:{i}")])
        # Строка действий
        kb_buttons.append([
            InlineKeyboardButton(text="Показать ответ", callback_data=f"reading_show_answer:{type_key}:{level_key}:{index}"),
            InlineKeyboardButton(text="Завершить", callback_data="reading_finish_session")
        ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    # Навигация по абзацам
    if len(paragraphs) > 1:
        nav_buttons = []
        if paragraph_idx > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀", callback_data=f"reading_prev_para:{type_key}:{level_key}:{index}:{paragraph_idx}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{paragraph_idx+1}/{len(paragraphs)}", callback_data="ignore"))
        if paragraph_idx < len(paragraphs) - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶", callback_data=f"reading_next_para:{type_key}:{level_key}:{index}:{paragraph_idx}"))
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
    type_key = callback.data.split(":", 1)[1]
    if type_key == "random":
        all_types = ["podbor", "truefalse", "choice", "fill", "match", "order"]
        type_key = random.choice(all_types)
    await callback.message.edit_text(
        f"Выбран тип: {TYPE_KEYS.get(type_key, type_key)}\nВыберите уровень:",
        reply_markup=get_level_keyboard(type_key),
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
    _, type_key, level_short = callback.data.split(":")
    user_id = callback.from_user.id

    type_json = TYPE_MAP.get(type_key, type_key)
    level_json = LEVEL_MAP.get(level_short, level_short)

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

    # Сохраняем состояние
    await state.update_data(
        type_key=type_json,
        level_key=level_json,
        index=index,
        paragraph_idx=0
    )

    # Генерируем полное сообщение
    text, keyboard = await render_task_message(user_id, type_json, level_json, index, paragraph_idx=0)
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
    _, type_key, level_key, index_str, curr_para_str = callback.data.split(":")
    index = int(index_str)
    curr_para = int(curr_para_str)
    user_id = callback.from_user.id

    task = get_task(type_key, level_key, index)
    if not task:
        await callback.answer("Ошибка задания")
        return

    paragraphs = task.get("paragraphs", [])
    if curr_para + 1 < len(paragraphs):
        new_para = curr_para + 1
        await state.update_data(paragraph_idx=new_para)
        text, keyboard = await render_task_message(user_id, type_key, level_key, index, new_para)
        if text:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reading_prev_para:"))
async def prev_paragraph(callback: CallbackQuery, state: FSMContext):
    _, type_key, level_key, index_str, curr_para_str = callback.data.split(":")
    index = int(index_str)
    curr_para = int(curr_para_str)
    user_id = callback.from_user.id

    if curr_para > 0:
        new_para = curr_para - 1
        await state.update_data(paragraph_idx=new_para)
        text, keyboard = await render_task_message(user_id, type_key, level_key, index, new_para)
        if text:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reading_answer:"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    _, type_key, level_key, index_str, chosen_idx_str = callback.data.split(":")
    index = int(index_str)
    chosen_idx = int(chosen_idx_str)
    user_id = callback.from_user.id

    task = get_task(type_key, level_key, index)
    if not task:
        await callback.answer("Задание не найдено")
        return

    correct = (chosen_idx == task["correct"])
    await update_user_stats(user_id, type_key, level_key, correct)

    if correct:
        await callback.answer("✅ Правильно!", show_alert=False)
    else:
        await callback.answer(
            f"❌ Неправильно. Правильный ответ: {task['options'][task['correct']]}",
            show_alert=False
        )

    # Переход к следующему заданию
    next_index = index + 1
    next_task = get_task(type_key, level_key, next_index)
    if not next_task:
        next_index = 0
        next_task = get_task(type_key, level_key, next_index)
        if not next_task:
            await callback.message.edit_text("Все задания пройдены! Начните заново или выберите другой уровень.")
            return

    await set_user_progress(user_id, type_key, level_key, next_index)
    await state.update_data(index=next_index, paragraph_idx=0)

    text, keyboard = await render_task_message(user_id, type_key, level_key, next_index, paragraph_idx=0)
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
    type_key = data.get("type_key")
    level_key = data.get("level_key")
    index = data.get("index")
    user_id = message.from_user.id

    if not all([type_key, level_key, index is not None]):
        await message.answer("Что-то пошло не так. Начните заново.")
        await state.clear()
        return

    task = get_task(type_key, level_key, index)
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

    await update_user_stats(user_id, type_key, level_key, correct)

    if correct:
        await message.answer("✅ Правильно!")
    else:
        await message.answer(f"❌ Неправильно. Правильный ответ: {correct_answer}")

    # Переход к следующему заданию
    next_index = index + 1
    next_task = get_task(type_key, level_key, next_index)
    if not next_task:
        next_index = 0
        next_task = get_task(type_key, level_key, next_index)
        if not next_task:
            await message.answer("Все задания пройдены! Начните заново или выберите другой уровень.")
            await state.clear()
            return

    await set_user_progress(user_id, type_key, level_key, next_index)
    await state.update_data(index=next_index, paragraph_idx=0)

    text, keyboard = await render_task_message(user_id, type_key, level_key, next_index, paragraph_idx=0)
    if text:
        if next_task.get("input_type") == "text":
            await state.set_state(ReadingStates.waiting_for_text)
        else:
            await state.set_state(None)
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("reading_show_answer:"))
async def show_answer(callback: CallbackQuery):
    _, type_key, level_key, index_str = callback.data.split(":")
    index = int(index_str)
    task = get_task(type_key, level_key, index)
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
    type_key = data.get("type_key")
    level_key = data.get("level_key")
    user_id = callback.from_user.id

    if type_key and level_key:
        correct, wrong = await get_user_stats(user_id, type_key, level_key)
        total = correct + wrong
        if total == 0:
            text = "Сессия завершена!\nВы не ответили ни на одно задание."
        else:
            accuracy = (correct / total * 100)
            text = f"Сессия завершена!\n✅ Правильно: {correct}\n❌ Ошибок: {wrong}\n🎯 Точность: {accuracy:.1f}%"
    else:
        text = "Сессия завершена!"

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="reading_back_to_main")]
        ]),
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()