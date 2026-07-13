from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from data.users import get_user_state, set_user_state
import json
import os

router = Router()

# Путь к файлу с заданиями
TASKS_FILE = "data/grammar_tasks.json"

# Загружаем задания из JSON и склеиваем все типы в один список
def load_all_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    all_tasks = []
    for task_type, tasks in data.items():
        all_tasks.extend(tasks)
    return all_tasks

ALL_TASKS = load_all_tasks()

# ---- Вспомогательные функции для работы с индексом ----
def get_grammar_index(user_id: int) -> int:
    state = get_user_state(user_id) or {}
    return state.get("grammar_index", 0)

def set_grammar_index(user_id: int, index: int):
    state = get_user_state(user_id) or {}
    state["grammar_index"] = index
    set_user_state(user_id, state)

def set_user_mode(user_id: int, mode: str):
    state = get_user_state(user_id) or {}
    state["mode"] = mode
    set_user_state(user_id, state)

def get_user_mode(user_id: int) -> str:
    state = get_user_state(user_id) or {}
    return state.get("mode", "")

# ---- Кнопки для карточки ----
def get_task_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data="grammar_show_answer"),
            InlineKeyboardButton(text="Завершить", callback_data="grammar_finish")
        ]
    ])

# ---- Отображение задания ----
async def show_grammar_task(message: Message, user_id: int, edit: bool = False):
    index = get_grammar_index(user_id)
    if index >= len(ALL_TASKS):
        index = 0
        set_grammar_index(user_id, index)
    task = ALL_TASKS[index]
    text = f"<b>Задание {index+1} из {len(ALL_TASKS)}</b>\n\n{task['question']}\n\nВведите ваш ответ в чат."
    keyboard = get_task_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# ---- Вход в режим ----
async def enter_grammar_mode(message: Message, user_id: int, edit: bool = False):
    set_user_mode(user_id, "grammar")
    await show_grammar_task(message, user_id, edit)

# ---- Обработчик кнопки "Показать ответ" ----
@router.callback_query(F.data == "grammar_show_answer")
async def show_answer_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    index = get_grammar_index(user_id)
    if index >= len(ALL_TASKS):
        index = 0
        set_grammar_index(user_id, index)
    task = ALL_TASKS[index]
    correct = task["correct"]
    await callback.answer()

    # Формируем строку с правильными ответами через " / "
    if isinstance(correct, str):
        answer_text = correct
    else:
        answer_text = " / ".join(correct)

    await callback.message.answer(f"Правильный ответ: {answer_text}")

    # Переходим к следующему заданию
    new_index = index + 1
    if new_index >= len(ALL_TASKS):
        new_index = 0
    set_grammar_index(user_id, new_index)
    await show_grammar_task(callback.message, user_id, edit=True)

# ---- Обработчик кнопки "Завершить" ----
@router.callback_query(F.data == "grammar_finish")
async def finish_grammar(callback: CallbackQuery):
    user_id = callback.from_user.id
    set_user_mode(user_id, "")  # сбрасываем режим
    await callback.answer()
    from handlers.main import show_main_menu
    await show_main_menu(callback.message, edit=True)

# ---- Обработчик текстовых ответов ----
@router.message(F.text & ~F.command)
async def handle_grammar_answer(message: Message):
    user_id = message.from_user.id
    if get_user_mode(user_id) != "grammar":
        await message.answer("Вы не в режиме грамматики. Используйте кнопки для входа.")
        return

    index = get_grammar_index(user_id)
    if index >= len(ALL_TASKS):
        index = 0
        set_grammar_index(user_id, index)
    task = ALL_TASKS[index]
    correct = task["correct"]
    user_answer = message.text.strip().lower()

    # Нормализуем правильные ответы
    if isinstance(correct, str):
        correct_variants = [correct.strip().lower()]
    else:
        correct_variants = [v.strip().lower() for v in correct]

    if user_answer in correct_variants:
        await message.answer("Правильно!")
    else:
        # Показываем первый правильный вариант (или можно все через /)
        first_correct = correct_variants[0]  # но мы хотим показать исходный вид, не в нижнем регистре
        # Лучше показать оригинальный (не нормализованный) ответ
        if isinstance(correct, str):
            display_answer = correct
        else:
            display_answer = correct[0]  # первый вариант
        await message.answer(f"Неправильно. Правильный ответ: {display_answer}")

    # Переходим к следующему заданию
    new_index = index + 1
    if new_index >= len(ALL_TASKS):
        new_index = 0
    set_grammar_index(user_id, new_index)
    await show_grammar_task(message, user_id, edit=False)