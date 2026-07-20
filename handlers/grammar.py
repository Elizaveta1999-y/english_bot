import json
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.db import get_grammar_index, set_grammar_index

router = Router()

class GrammarStates(StatesGroup):
    active = State()

# ---------- Загрузка заданий из JSON ----------
TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/grammar_tasks.json")

def load_all_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    all_tasks = []
    for category, tasks in data.items():
        all_tasks.extend(tasks)
    return all_tasks

ALL_TASKS = load_all_tasks()

# ---------- Клавиатура ----------
def get_task_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать ответ", callback_data="grammar_show_answer")],
        [InlineKeyboardButton(text="Завершить", callback_data="grammar_finish")]
    ])

# ---------- Отображение задания ----------
async def show_grammar_task(message: Message, user_id: int, state: FSMContext, edit: bool = False):
    index = await get_grammar_index(user_id)
    if index >= len(ALL_TASKS):
        index = 0
        await set_grammar_index(user_id, index)
    task = ALL_TASKS[index]
    text = f"<b>Задание {index+1} из {len(ALL_TASKS)}</b>\n\n{task['question']}\n\nВведите ваш ответ в чат."
    keyboard = get_task_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(GrammarStates.active)

async def enter_grammar_mode(message: Message, user_id: int, state: FSMContext, edit: bool = False):
    await state.set_state(GrammarStates.active)
    await show_grammar_task(message, user_id, state, edit)

# ---------- Хендлеры ----------
@router.callback_query(F.data == "grammar_show_answer", GrammarStates.active)
async def show_answer_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    index = await get_grammar_index(user_id)
    if index >= len(ALL_TASKS):
        index = 0
        await set_grammar_index(user_id, index)
    task = ALL_TASKS[index]
    correct = task["correct"]
    await callback.answer()
    if isinstance(correct, str):
        answer_text = correct
    else:
        answer_text = " / ".join(correct)
    await callback.message.answer(f"Правильный ответ: {answer_text}")
    new_index = index + 1
    if new_index >= len(ALL_TASKS):
        new_index = 0
    await set_grammar_index(user_id, new_index)
    await show_grammar_task(callback.message, user_id, state, edit=True)

@router.callback_query(F.data == "grammar_finish", GrammarStates.active)
async def finish_grammar(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)

@router.message(GrammarStates.active, F.text)
async def handle_grammar_answer(message: Message, state: FSMContext):
    user_id = message.from_user.id
    index = await get_grammar_index(user_id)
    if index >= len(ALL_TASKS):
        index = 0
        await set_grammar_index(user_id, index)
    task = ALL_TASKS[index]
    correct = task["correct"]
    user_answer = message.text.strip().lower()
    if isinstance(correct, str):
        correct_variants = [correct.strip().lower()]
        display_answer = correct
    else:
        correct_variants = [v.strip().lower() for v in correct]
        display_answer = correct[0]
    if user_answer in correct_variants:
        await message.answer("✅ Правильно!")
    else:
        await message.answer(f"❌ Неправильно. Правильный ответ: {display_answer}")
    new_index = index + 1
    if new_index >= len(ALL_TASKS):
        new_index = 0
    await set_grammar_index(user_id, new_index)
    await show_grammar_task(message, user_id, state, edit=False)

# Хендлер для сообщений вне режима грамматики
@router.message(F.text, F.state != GrammarStates.active)
async def not_in_grammar_mode(message: Message):
    await message.answer("Вы не в режиме грамматики. Используйте кнопки в главном меню.")