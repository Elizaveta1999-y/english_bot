from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold
from data.reading_loader import get_task, TASKS
from utils.redis_utils import (
    get_global_welcome_index, increment_global_welcome_index,
    get_user_progress, set_user_progress, get_user_stats, update_user_stats, reset_user_progress
)
from states.reading_states import ReadingStates
import re

router = Router()

# -------------------- Приветственные сообщения --------------------
READING_WELCOME_MESSAGES = [
    "<b>📖 Чтение</b>\n\n<i>Чтение — это ключ к расширению словарного запаса и пониманию структур языка. Регулярно читайте тексты разного уровня и учитесь выделять главное.</i>\n\nВыберите тип задания и уровень — и тренируйтесь в удобном темпе.",
    "<b>📖 Чтение</b>\n\n<i>Умение быстро читать и понимать текст пригодится в любом контексте: от экзаменов до работы. Начните с коротких текстов и постепенно увеличивайте сложность.</i>\n\nГотовы попробовать?",
    "<b>📖 Чтение</b>\n\n<i>Чтение на английском — это не только полезно, но и увлекательно. Выбирайте задания, которые вам интересны, и прокачивайте навык.</i>\n\nКакой тип выберете сегодня?",
    "<b>📖 Чтение</b>\n\n<i>Навык чтения включает в себя понимание деталей, поиск информации и интерпретацию текста. Тренируйте все аспекты с нашими заданиями.</i>\n\nПриступим?",
    "<b>📖 Чтение</b>\n\n<i>Читайте, анализируйте, отвечайте на вопросы — и вы заметите, как тексты становятся понятнее с каждым разом.</i>\n\nВыберите задание и уровень."
]

# -------------------- Вспомогательные функции --------------------
def get_type_choice_keyboard():
    """Клавиатура выбора типа задания (7 кнопок + Назад)."""
    buttons = [
        [InlineKeyboardButton(text="🥈 Подбор заголовка", callback_data="reading_type:Подбор_заголовка")],
        [InlineKeyboardButton(text="⚖️ True/False/Not stated", callback_data="reading_type:True_False_Not_stated")],
        [InlineKeyboardButton(text="☑️ Вопросы с выбором ответа", callback_data="reading_type:Вопросы_с_выбором_ответа")],
        [InlineKeyboardButton(text="🔄 Заполнение пропусков", callback_data="reading_type:Заполнение_пропусков")],
        [InlineKeyboardButton(text="🟰 Соотношение слова с определением", callback_data="reading_type:Соотношение_слова_с_определением")],
        [InlineKeyboardButton(text="📄 Восстановление порядка абзацев", callback_data="reading_type:Восстановление_порядка_абзацев")],
        [InlineKeyboardButton(text="🎲 Случайный тип", callback_data="reading_type:Случайный_тип")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_keyboard(type_key: str):
    """Клавиатура выбора уровня (Новичок, Любитель, Эксперт, Назад)."""
    buttons = [
        [InlineKeyboardButton(text="🌱 Новичок", callback_data=f"reading_level:{type_key}:Новичок")],
        [InlineKeyboardButton(text="🔥 Любитель", callback_data=f"reading_level:{type_key}:Любитель")],
        [InlineKeyboardButton(text="⚡ Эксперт", callback_data=f"reading_level:{type_key}:Эксперт")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="reading_back_to_types")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_keyboard(type_key: str, level_key: str, index: int, total: int):
    """
    Создаёт клавиатуру для карточки задания:
    - навигация по абзацам (◀ 1/5 ▶)
    - кнопка "Показать ответ" (или просто отсутствует, т.к. мы показываем ответ автоматически)
    - кнопка "Завершить"
    - кнопка "Назад" (выход из режима)
    """
    # Навигация по абзацам пока не реализована в полном объёме — пока просто номер абзаца.
    # Но мы можем добавить кнопки, но для простоты пока опустим.
    # Позже добавим отдельные обработчики для листания.
    buttons = [
        [InlineKeyboardButton(text="📖 Показать ответ", callback_data=f"reading_show_answer:{type_key}:{level_key}:{index}")],
        [InlineKeyboardButton(text="❌ Завершить", callback_data="reading_finish_session")],
        [InlineKeyboardButton(text="🔙 Выйти", callback_data="reading_back_to_types")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_text_input_keyboard(type_key: str, level_key: str, index: int):
    """Клавиатура для заданий с текстовым вводом (без кнопок ответов)."""
    buttons = [
        [InlineKeyboardButton(text="📖 Показать ответ", callback_data=f"reading_show_answer:{type_key}:{level_key}:{index}")],
        [InlineKeyboardButton(text="❌ Завершить", callback_data="reading_finish_session")],
        [InlineKeyboardButton(text="🔙 Выйти", callback_data="reading_back_to_types")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_task_message(task, type_key: str, level_key: str, index: int, paragraph_idx: int = 0):
    """
    Формирует текст сообщения с текущим абзацем и заданием.
    Возвращает (текст, клавиатура).
    """
    if not task:
        return None, None
    # Получаем текущий абзац
    paragraphs = task.get("paragraphs", [])
    if not paragraphs or paragraph_idx >= len(paragraphs):
        paragraph_idx = 0
    current_paragraph = paragraphs[paragraph_idx]
    
    # Формируем текст
    text = f"<b>Режим: {type_key}</b>\n\n"
    text += f"<i>{current_paragraph}</i>\n\n"
    text += f"<b>{task.get('question', '')}</b>\n\n"
    
    # Для типов с выбором — добавляем подсказку для выбора
    if task.get("input_type") == "text":
        text += "Введите ответ в чат.\n"
    else:
        # Добавляем варианты (они будут кнопками)
        pass
    
    # Клавиатура
    if task.get("input_type") == "text":
        keyboard = get_text_input_keyboard(type_key, level_key, index)
    else:
        # Генерируем кнопки вариантов
        options = task.get("options", [])
        kb_buttons = []
        for i, opt in enumerate(options):
            kb_buttons.append([InlineKeyboardButton(text=opt, callback_data=f"reading_answer:{type_key}:{level_key}:{index}:{i}")])
        # Добавляем служебные кнопки
        kb_buttons.append([InlineKeyboardButton(text="📖 Показать ответ", callback_data=f"reading_show_answer:{type_key}:{level_key}:{index}")])
        kb_buttons.append([InlineKeyboardButton(text="❌ Завершить", callback_data="reading_finish_session")])
        kb_buttons.append([InlineKeyboardButton(text="🔙 Выйти", callback_data="reading_back_to_types")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    # Добавим навигацию по абзацам, если абзацев больше одного
    if len(paragraphs) > 1:
        nav_buttons = []
        if paragraph_idx > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀", callback_data=f"reading_prev_para:{type_key}:{level_key}:{index}:{paragraph_idx}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{paragraph_idx+1}/{len(paragraphs)}", callback_data="ignore"))
        if paragraph_idx < len(paragraphs) - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶", callback_data=f"reading_next_para:{type_key}:{level_key}:{index}:{paragraph_idx}"))
        # Вставляем эту строку в начало клавиатуры
        new_kb = [nav_buttons] + keyboard.inline_keyboard
        keyboard = InlineKeyboardMarkup(inline_keyboard=new_kb)
    
    return text, keyboard

# -------------------- Обработчики --------------------
@router.callback_query(F.data == "start_reading")
async def start_reading(callback: CallbackQuery):
    # Показываем приветственное сообщение (глобальный индекс)
    global_idx = get_global_welcome_index()
    welcome_text = READING_WELCOME_MESSAGES[global_idx]
    # Можно обновлять индекс при каждом показе? Или раз в сутки. Пока просто показываем.
    # Для обновления раз в сутки нужен отдельный механизм (крон), пока оставим как есть.
    await callback.message.edit_text(welcome_text, reply_markup=get_type_choice_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "reading_back_to_main")
async def back_to_main(callback: CallbackQuery):
    from .start import show_main_menu  # импортируем функцию главного меню
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("reading_type:"))
async def choose_type(callback: CallbackQuery):
    type_key = callback.data.split(":", 1)[1]
    if type_key == "Случайный_тип":
        # Выбираем случайный тип из доступных (кроме самого себя)
        import random
        all_types = ["Подбор_заголовка", "True_False_Not_stated", "Вопросы_с_выбором_ответа", 
                     "Заполнение_пропусков", "Соотношение_слова_с_определением", "Восстановление_порядка_абзацев"]
        type_key = random.choice(all_types)
    # Сохраняем выбранный тип в состоянии? Можно в callback.data передать, но проще сохранить в Redis или в FSM.
    # Для простоты будем передавать в callback_data при выборе уровня.
    await callback.message.edit_text(f"Выбран тип: {type_key}\nВыберите уровень:", reply_markup=get_level_keyboard(type_key), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "reading_back_to_types")
async def back_to_types(callback: CallbackQuery):
    # Возврат к выбору типа
    await callback.message.edit_text("Выберите тип задания:", reply_markup=get_type_choice_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reading_level:"))
async def choose_level(callback: CallbackQuery, state: FSMContext):
    _, type_key, level_key = callback.data.split(":")
    user_id = callback.from_user.id
    # Получаем текущий прогресс
    index = get_user_progress(user_id, type_key, level_key)
    task = get_task(type_key, level_key, index)
    if not task:
        # Если заданий нет или индекс вышел за границы (например, 100), сбрасываем на 0
        index = 0
        set_user_progress(user_id, type_key, level_key, index)
        task = get_task(type_key, level_key, index)
        if not task:
            await callback.message.edit_text("Задания для этого уровня пока отсутствуют. Попробуйте другой уровень.")
            await callback.answer()
            return
    # Сохраняем в FSM текущий тип, уровень, индекс, чтобы потом знать, что пользователь отвечает
    await state.update_data(type_key=type_key, level_key=level_key, index=index)
    # Отображаем первую карточку
    text, keyboard = build_task_message(task, type_key, level_key, index, paragraph_idx=0)
    if text is None:
        await callback.message.edit_text("Ошибка загрузки задания.")
        await callback.answer()
        return
    # Сохраним текущий абзац в FSM
    await state.update_data(paragraph_idx=0)
    # Проверяем, если задание с текстовым вводом — устанавливаем состояние ожидания
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
    data = await state.get_data()
    # Берём задание из памяти или заново
    task = get_task(type_key, level_key, index)
    if not task:
        await callback.answer("Ошибка задания")
        return
    paragraphs = task.get("paragraphs", [])
    if curr_para + 1 < len(paragraphs):
        new_para = curr_para + 1
        await state.update_data(paragraph_idx=new_para)
        text, keyboard = build_task_message(task, type_key, level_key, index, new_para)
        if text:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reading_prev_para:"))
async def prev_paragraph(callback: CallbackQuery, state: FSMContext):
    _, type_key, level_key, index_str, curr_para_str = callback.data.split(":")
    index = int(index_str)
    curr_para = int(curr_para_str)
    if curr_para > 0:
        new_para = curr_para - 1
        await state.update_data(paragraph_idx=new_para)
        task = get_task(type_key, level_key, index)
        if task:
            text, keyboard = build_task_message(task, type_key, level_key, index, new_para)
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
    # Обновляем статистику
    update_user_stats(user_id, type_key, level_key, correct)
    # Получаем новую статистику для отображения
    correct_count, wrong_count = get_user_stats(user_id, type_key, level_key)
    # Ответное сообщение
    if correct:
        await callback.answer("✅ Правильно!", show_alert=False)
    else:
        await callback.answer(f"❌ Неправильно. Правильный ответ: {task['options'][task['correct']]}", show_alert=False)
    # Переходим к следующему заданию
    next_index = index + 1
    # Проверяем, есть ли следующее задание
    next_task = get_task(type_key, level_key, next_index)
    if not next_task:
        # Если задания кончились, сбрасываем на 0 (циклически)
        next_index = 0
        next_task = get_task(type_key, level_key, next_index)
        if not next_task:
            # Совсем нет заданий
            await callback.message.edit_text("Все задания пройдены! Начните заново или выберите другой уровень.")
            return
    # Сохраняем новый индекс
    set_user_progress(user_id, type_key, level_key, next_index)
    await state.update_data(index=next_index, paragraph_idx=0)
    # Отображаем новое задание
    text, keyboard = build_task_message(next_task, type_key, level_key, next_index, paragraph_idx=0)
    if task.get("input_type") == "text":
        await state.set_state(ReadingStates.waiting_for_text)
    else:
        await state.set_state(None)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(ReadingStates.waiting_for_text)
async def handle_text_answer(message: Message, state: FSMContext):
    # Обработка текстовых ответов (заполнение пропусков, восстановление порядка)
    data = await state.get_data()
    type_key = data.get("type_key")
    level_key = data.get("level_key")
    index = data.get("index")
    if not all([type_key, level_key, index is not None]):
        await message.answer("Что-то пошло не так. Начните заново.")
        await state.clear()
        return
    task = get_task(type_key, level_key, index)
    if not task:
        await message.answer("Задание не найдено.")
        await state.clear()
        return
    # Получаем правильный ответ
    correct_answer = task.get("correct")
    user_input = message.text.strip()
    # Приводим к нижнему регистру, убираем лишние пробелы, заменяем разделители
    # Для заполнения пропусков correct - список, для порядка - строка
    if isinstance(correct_answer, list):
        # Разбиваем ввод по точке с запятой
        user_parts = [p.strip().lower() for p in user_input.split(";") if p.strip()]
        correct_parts = [p.strip().lower() for p in correct_answer]
        # Сравниваем списки
        if user_parts == correct_parts:
            correct = True
        else:
            correct = False
    else:
        # Для порядка абзацев - строка
        # Очищаем от лишних пробелов, приводим к нижнему регистру
        user_clean = "".join(user_input.split()).lower()
        correct_clean = "".join(str(correct_answer).split()).lower()
        correct = (user_clean == correct_clean)
    
    user_id = message.from_user.id
    update_user_stats(user_id, type_key, level_key, correct)
    correct_count, wrong_count = get_user_stats(user_id, type_key, level_key)
    
    # Ответ
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
    set_user_progress(user_id, type_key, level_key, next_index)
    await state.update_data(index=next_index, paragraph_idx=0)
    # Отображаем новое задание
    text, keyboard = build_task_message(next_task, type_key, level_key, next_index, paragraph_idx=0)
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
    await callback.answer(f"Правильный ответ: {correct}\n{explanation}", show_alert=True)
    # Не переходим автоматически, пусть пользователь сам завершит или продолжит

@router.callback_query(F.data == "reading_finish_session")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    # Завершаем сессию, показываем статистику за эту сессию (можно взять из Redis)
    data = await state.get_data()
    type_key = data.get("type_key")
    level_key = data.get("level_key")
    if type_key and level_key:
        correct, wrong = get_user_stats(callback.from_user.id, type_key, level_key)
        total = correct + wrong
        if total == 0:
            text = "Сессия завершена!\nВы не ответили ни на одно задание."
        else:
            accuracy = (correct / total * 100) if total > 0 else 0
            text = f"Сессия завершена!\n✅ Правильно: {correct}\n❌ Ошибок: {wrong}\n🎯 Точность: {accuracy:.1f}%"
    else:
        text = "Сессия завершена!"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В меню", callback_data="reading_back_to_main")]
    ]), parse_mode="HTML")
    await state.clear()
    await callback.answer()

# Обработчик для игнорирования нажатий на навигационную кнопку с номером страницы
@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()