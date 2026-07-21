from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from data.users import get_user_state, set_user_state
import json
from typing import List, Dict, Any

router = Router()

# Путь к файлу с заданиями
TASKS_FILE = "data/grammar_tasks.json"

# Загружаем задания из JSON
def load_tasks() -> Dict[str, List[Dict]]:
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

RAW_TASKS = load_tasks()

# Разбиваем задания каждого типа на три уровня
def split_into_levels(task_list: List[Dict]) -> Dict[str, List[Dict]]:
    total = len(task_list)
    if total == 0:
        return {"Новичок": [], "Любитель": [], "Эксперт": []}
    third = total // 3
    if third == 0:
        return {"Новичок": task_list, "Любитель": [], "Эксперт": []}
    return {
        "Новичок": task_list[:third],
        "Любитель": task_list[third:2*third],
        "Эксперт": task_list[2*third:]
    }

TASKS_BY_TYPE_LEVEL = {}
for task_type, tasks in RAW_TASKS.items():
    TASKS_BY_TYPE_LEVEL[task_type] = split_into_levels(tasks)

TASK_TYPES = list(TASKS_BY_TYPE_LEVEL.keys())
LEVELS = ["Новичок", "Любитель", "Эксперт"]

TYPE_EMOJIS = {
    "раскрытие_скобок": "📑",
    "вставка_пропусков": "↪️",
    "to_be_выбор": "⚖️",
    "to_be_скобки": "🗞️",
    "добавьте_s": "➕",
    "множественное_число": "🖇️",
    "единственное_число": "📎",
    "отрицание": "➖"
}

LEVEL_EMOJIS = {
    "Новичок": "🌱",
    "Любитель": "📚",
    "Эксперт": "🎓"
}

def get_progress_key(user_id: int, task_type: str, level: str) -> str:
    return f"grammar:{user_id}:{task_type}:{level}"

def get_progress(user_id: int, task_type: str, level: str) -> Dict[str, Any]:
    state = get_user_state(user_id) or {}
    key = get_progress_key(user_id, task_type, level)
    default = {
        "index": 0,
        "correct": 0,
        "wrong": 0,
        "wrong_ids": [],
        "session_correct": 0,
        "session_wrong": 0
    }
    return state.get(key, default)

def save_progress(user_id: int, task_type: str, level: str, progress: Dict):
    state = get_user_state(user_id) or {}
    key = get_progress_key(user_id, task_type, level)
    state[key] = progress
    set_user_state(user_id, state)

def reset_progress(user_id: int, task_type: str, level: str):
    save_progress(user_id, task_type, level, {
        "index": 0,
        "correct": 0,
        "wrong": 0,
        "wrong_ids": [],
        "session_correct": 0,
        "session_wrong": 0
    })

def get_tasks(task_type: str, level: str) -> List[Dict]:
    return TASKS_BY_TYPE_LEVEL.get(task_type, {}).get(level, [])

# ---- Клавиатуры ----

def get_type_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for t in TASK_TYPES:
        emoji = TYPE_EMOJIS.get(t, "")
        buttons.append([InlineKeyboardButton(text=f"{emoji} {t}", callback_data=f"grammar_type_{t}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="grammar_back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_level_keyboard(task_type: str) -> InlineKeyboardMarkup:
    buttons = []
    for level in LEVELS:
        emoji = LEVEL_EMOJIS.get(level, "")
        buttons.append([InlineKeyboardButton(text=f"{emoji} {level}", callback_data=f"grammar_level_{task_type}_{level}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="grammar_back_to_types")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_progress_controls_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Работа над ошибками", callback_data="grammar_work_errors")],
        [InlineKeyboardButton(text="Сбросить прогресс", callback_data="grammar_reset_progress")]
    ])

def get_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data="grammar_show_answer"),
            InlineKeyboardButton(text="Завершить", callback_data="grammar_finish")
        ]
    ])

# ---- Отображение прогресса и управления ----

async def show_progress_message(message: Message, user_id: int, task_type: str, level: str, edit: bool = False):
    progress = get_progress(user_id, task_type, level)
    type_display = task_type
    level_display = level
    text = f"<b>Режим:</b> {TYPE_EMOJIS.get(task_type, '')} {type_display}\n"
    text += f"<b>Уровень:</b> {LEVEL_EMOJIS.get(level, '')} {level_display}\n\n"
    text += f"Ваш прогресс:\n"
    text += f"✔️ Правильно: {progress['correct']}\n"
    text += f"✖️ Ошибок: {progress['wrong']}"
    keyboard = get_progress_controls_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# ---- Отображение карточки задания ----

async def show_task_card(message: Message, user_id: int, task_type: str, level: str, edit: bool = False):
    tasks = get_tasks(task_type, level)
    if not tasks:
        await message.answer("Заданий для этого типа и уровня пока нет. Выберите другой уровень.", reply_markup=get_level_keyboard(task_type))
        return

    progress = get_progress(user_id, task_type, level)
    index = progress["index"]
    if index >= len(tasks):
        reset_progress(user_id, task_type, level)
        progress = get_progress(user_id, task_type, level)
        index = 0

    task = tasks[index]
    text = task['question']
    keyboard = get_task_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)

# ---- Вход в режим ----

async def enter_grammar_mode(message: Message, user_id: int, edit: bool = False, state=None):
    text = "🔀 Грамматика\n\nВыберите тип задания:"
    keyboard = get_type_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)

# ---- Обработчики ----

@router.callback_query(F.data == "start_grammar")
async def start_grammar(callback: CallbackQuery):
    await callback.answer()
    await enter_grammar_mode(callback.message, callback.from_user.id, edit=True)

@router.callback_query(F.data == "grammar_back_to_menu")
async def back_to_main_menu(callback: CallbackQuery):
    await callback.answer()
    from handlers.main import show_main_menu
    await show_main_menu(callback.message, edit=True)

@router.callback_query(F.data == "grammar_back_to_types")
async def back_to_types(callback: CallbackQuery):
    await callback.answer()
    await enter_grammar_mode(callback.message, callback.from_user.id, edit=True)

@router.callback_query(F.data.startswith("grammar_type_"))
async def select_type(callback: CallbackQuery):
    await callback.answer()
    task_type = callback.data.replace("grammar_type_", "")
    text = f"Выберите уровень сложности для типа: {task_type}"
    keyboard = get_level_keyboard(task_type)
    await callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data.startswith("grammar_level_"))
async def select_level(callback: CallbackQuery):
    await callback.answer()
    data = callback.data[len("grammar_level_"):]
    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        await callback.message.answer("Ошибка в данных. Попробуйте ещё раз.")
        return
    task_type = parts[0]
    level = parts[1]
    user_id = callback.from_user.id

    tasks = get_tasks(task_type, level)
    if not tasks:
        await callback.message.answer(
            "Заданий для этого типа и уровня пока нет. Выберите другой уровень.",
            reply_markup=get_level_keyboard(task_type)
        )
        return

    # Сохраняем текущие тип и уровень в состоянии пользователя
    state = get_user_state(user_id) or {}
    state["grammar_current_type"] = task_type
    state["grammar_current_level"] = level
    # Обнуляем сессионные счётчики
    progress = get_progress(user_id, task_type, level)
    progress["session_correct"] = 0
    progress["session_wrong"] = 0
    save_progress(user_id, task_type, level, progress)
    set_user_state(user_id, state)

    # Показываем сообщение с прогрессом и управлением
    await show_progress_message(callback.message, user_id, task_type, level, edit=True)
    # Затем показываем карточку задания
    await show_task_card(callback.message, user_id, task_type, level, edit=False)

# ---- Обработчики кнопок на карточке ----

@router.callback_query(F.data == "grammar_show_answer")
async def show_answer(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    state = get_user_state(user_id) or {}
    task_type = state.get("grammar_current_type")
    level = state.get("grammar_current_level")
    if not task_type or not level:
        await callback.message.answer("Ошибка: не выбран тип или уровень. Начните заново.")
        return

    tasks = get_tasks(task_type, level)
    progress = get_progress(user_id, task_type, level)
    index = progress["index"]
    if index >= len(tasks):
        reset_progress(user_id, task_type, level)
        progress = get_progress(user_id, task_type, level)
        index = 0

    task = tasks[index]
    correct = task["correct"]
    explanation = task.get("explanation", "")
    if isinstance(correct, list):
        answer_text = " / ".join(correct)
    else:
        answer_text = correct

    # Отправляем ответ с объяснением
    text = f"Правильный ответ: {answer_text}\n{explanation}"
    await callback.message.answer(text)

    # Переход к следующему заданию (увеличиваем индекс)
    progress["index"] += 1
    if progress["index"] >= len(tasks):
        reset_progress(user_id, task_type, level)
        await callback.message.answer("Поздравляем! Вы прошли все задания этого уровня. Прогресс сброшен.")
        await enter_grammar_mode(callback.message, user_id, edit=True)
        return
    save_progress(user_id, task_type, level, progress)
    # Показываем новую карточку задания
    await show_task_card(callback.message, user_id, task_type, level, edit=False)

@router.callback_query(F.data == "grammar_finish")
async def finish_grammar(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    state = get_user_state(user_id) or {}
    task_type = state.get("grammar_current_type")
    level = state.get("grammar_current_level")
    if not task_type or not level:
        await callback.message.answer("Ошибка: не выбран тип или уровень.")
        return

    progress = get_progress(user_id, task_type, level)
    session_correct = progress.get("session_correct", 0)
    session_wrong = progress.get("session_wrong", 0)
    total = session_correct + session_wrong

    # Формируем фидбек
    if total == 0:
        text = "Вы не ответили ни на одно задание в этой сессии."
    else:
        text = f"Сессия завершена.\n✔️ Правильно: {session_correct}\n✖️ Ошибок: {session_wrong}"

    # Обнуляем сессионные счётчики (чтобы при следующем входе были нулевые)
    progress["session_correct"] = 0
    progress["session_wrong"] = 0
    save_progress(user_id, task_type, level, progress)

    # Отправляем фидбек
    await callback.message.answer(text)
    # Возвращаемся в главное меню
    from handlers.main import show_main_menu
    await show_main_menu(callback.message, edit=True)

@router.callback_query(F.data == "grammar_reset_progress")
async def reset_progress_callback(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    state = get_user_state(user_id) or {}
    task_type = state.get("grammar_current_type")
    level = state.get("grammar_current_level")
    if not task_type or not level:
        await callback.message.answer("Ошибка: не выбран тип или уровень.")
        return
    reset_progress(user_id, task_type, level)
    await callback.message.answer("Прогресс сброшен.")
    # Обновляем сообщение с прогрессом и карточку
    await show_progress_message(callback.message, user_id, task_type, level, edit=True)
    await show_task_card(callback.message, user_id, task_type, level, edit=False)

@router.callback_query(F.data == "grammar_work_errors")
async def work_on_errors(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    state = get_user_state(user_id) or {}
    task_type = state.get("grammar_current_type")
    level = state.get("grammar_current_level")
    if not task_type or not level:
        await callback.message.answer("Ошибка: не выбран тип или уровень.")
        return
    progress = get_progress(user_id, task_type, level)
    wrong_ids = progress.get("wrong_ids", [])
    if not wrong_ids:
        await callback.message.answer("У вас нет ошибок в этом уровне. Отличная работа!")
        return
    all_tasks = get_tasks(task_type, level)
    error_tasks = [t for t in all_tasks if t.get("id") in wrong_ids]
    if not error_tasks:
        await callback.message.answer("Задания с ошибками не найдены. Возможно, они были удалены.")
        return
    state["grammar_error_tasks"] = error_tasks
    state["grammar_error_index"] = 0
    set_user_state(user_id, state)
    await show_error_task(callback.message, user_id, edit=True)

# ---- Работа над ошибками ----

async def show_error_task(message: Message, user_id: int, edit: bool = False):
    state = get_user_state(user_id) or {}
    error_tasks = state.get("grammar_error_tasks", [])
    error_index = state.get("grammar_error_index", 0)
    if error_index >= len(error_tasks):
        await message.answer("Все ошибки исправлены! Отличная работа.")
        task_type = state.get("grammar_current_type")
        level = state.get("grammar_current_level")
        if task_type and level:
            await show_progress_message(message, user_id, task_type, level, edit=True)
            await show_task_card(message, user_id, task_type, level, edit=False)
        else:
            await enter_grammar_mode(message, user_id, edit=True)
        return
    task = error_tasks[error_index]
    text = "🔴 Работа над ошибками\n\n" + task['question']
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать ответ", callback_data="grammar_error_show_answer")],
        [InlineKeyboardButton(text="Завершить работу над ошибками", callback_data="grammar_error_finish")]
    ])
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)

@router.callback_query(F.data == "grammar_error_show_answer")
async def show_error_answer(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    state = get_user_state(user_id) or {}
    error_tasks = state.get("grammar_error_tasks", [])
    error_index = state.get("grammar_error_index", 0)
    if error_index >= len(error_tasks):
        await callback.message.answer("Нет заданий для показа.")
        return
    task = error_tasks[error_index]
    correct = task["correct"]
    explanation = task.get("explanation", "")
    if isinstance(correct, list):
        answer_text = " / ".join(correct)
    else:
        answer_text = correct
    await callback.message.answer(f"Правильный ответ: {answer_text}\n{explanation}")
    state["grammar_error_index"] = error_index + 1
    set_user_state(user_id, state)
    await show_error_task(callback.message, user_id, edit=True)

@router.callback_query(F.data == "grammar_error_finish")
async def finish_error_mode(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    state = get_user_state(user_id) or {}
    state.pop("grammar_error_tasks", None)
    state.pop("grammar_error_index", None)
    set_user_state(user_id, state)
    task_type = state.get("grammar_current_type")
    level = state.get("grammar_current_level")
    if task_type and level:
        await show_progress_message(callback.message, user_id, task_type, level, edit=True)
        await show_task_card(callback.message, user_id, task_type, level, edit=False)
    else:
        await enter_grammar_mode(callback.message, user_id, edit=True)

# ---- Обработчик текстовых ответов (в обычном режиме) ----

@router.message(F.text & ~F.command)
async def handle_grammar_answer(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id) or {}
    task_type = state.get("grammar_current_type")
    level = state.get("grammar_current_level")
    if not task_type or not level:
        await message.answer("Вы не в режиме грамматики. Используйте кнопки для входа.")
        return

    tasks = get_tasks(task_type, level)
    progress = get_progress(user_id, task_type, level)
    index = progress.get("index", 0)
    if index >= len(tasks):
        reset_progress(user_id, task_type, level)
        await message.answer("Поздравляем! Вы прошли все задания этого уровня. Прогресс сброшен.")
        await enter_grammar_mode(message, user_id, edit=False)
        return

    task = tasks[index]
    correct = task["correct"]
    explanation = task.get("explanation", "")
    user_answer = message.text.strip().lower()
    if isinstance(correct, str):
        correct_variants = [correct.strip().lower()]
    else:
        correct_variants = [v.strip().lower() for v in correct]

    if user_answer in correct_variants:
        await message.answer("Правильно!")
        progress["correct"] += 1
        progress["session_correct"] += 1
        if task.get("id") in progress.get("wrong_ids", []):
            progress["wrong_ids"].remove(task["id"])
    else:
        if isinstance(correct, list):
            display_answer = " / ".join(correct)
        else:
            display_answer = correct
        await message.answer(f"Неправильно. Правильный ответ: {display_answer}\n{explanation}")
        progress["wrong"] += 1
        progress["session_wrong"] += 1
        if task.get("id") not in progress.get("wrong_ids", []):
            progress.setdefault("wrong_ids", []).append(task["id"])

    progress["index"] += 1
    if progress["index"] >= len(tasks):
        reset_progress(user_id, task_type, level)
        await message.answer("Поздравляем! Вы прошли все задания этого уровня. Прогресс сброшен.")
        await enter_grammar_mode(message, user_id, edit=False)
        return

    save_progress(user_id, task_type, level, progress)
    # Показываем новую карточку задания
    await show_task_card(message, user_id, task_type, level, edit=False)