import json
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

# ---------- Загрузка заданий ----------
TASKS_FILE = os.path.join(os.path.dirname(__file__), "../data/writing_tasks.json")

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

ALL_TASKS = load_tasks()

print("=== WRITING TASKS LOADED (FINAL) ===")
print(f"Keys: {list(ALL_TASKS.keys())}")

# ---------- Состояния FSM ----------
class WritingStates(StatesGroup):
    choosing_type = State()
    choosing_level = State()
    waiting_answer = State()

# ---------- Клавиатуры ----------
def get_types_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📧 Email", callback_data="type_email"),
            InlineKeyboardButton(text="📝 Эссе", callback_data="type_essay")
        ],
        [
            InlineKeyboardButton(text="📱 Пост в соцсети", callback_data="type_post"),
            InlineKeyboardButton(text="💬 Диалог", callback_data="type_dialogue")
        ],
        [
            InlineKeyboardButton(text="📖 История", callback_data="type_story"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ])

def get_levels_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌱 Новичок", callback_data="level_beginner"),
            InlineKeyboardButton(text="🔥 Любитель", callback_data="level_intermediate")
        ],
        [
            InlineKeyboardButton(text="🧠 Эксперт", callback_data="level_advanced"),
            InlineKeyboardButton(text="🔙 Назад к типам", callback_data="back_to_types")
        ]
    ])

def get_action_keyboard(short_type: str, level: str, index: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Показать пример", callback_data=f"writing_show_sample:{short_type}:{level}:{index}"),
            InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_writing")
        ]
    ])

# ---------- Показать типы ----------
async def show_task_types(message: Message, edit: bool = False):
    text = (
        "✍️ *Режим Письмо (FINAL)*\n\n"
        "Выберите тип задания:\n"
        "📧 *Email*\n"
        "📝 *Эссе*\n"
        "📱 *Пост*\n"
        "💬 *Диалог*\n"
        "📖 *История*"
    )
    keyboard = get_types_keyboard()
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ---------- Обработчики ----------
@router.callback_query(F.data.startswith("type_"))
async def type_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_type = callback.data.split("_")[1]
    await state.update_data(task_type=task_type)
    await state.set_state(WritingStates.choosing_level)
    text = f"Вы выбрали тип: *{task_type.upper()}*.\nТеперь выберите уровень:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery, state: FSMContext):
    print(f"!!! LEVEL CHOSEN CALLBACK: {callback.data}")
    await callback.answer()
    level = callback.data.split("_")[1]
    await callback.message.edit_text(f"✅ Вы выбрали уровень: {level}. Это тестовое сообщение. Если вы это видите, обработчик работает!")

# ---------- УНИВЕРСАЛЬНЫЙ ЛОГГЕР ВСЕХ CALLBACK ----------
@router.callback_query()
async def catch_all_callbacks(callback: CallbackQuery):
    print(f"CATCH ALL: {callback.data}")
    await callback.answer()

# ---------- Остальные обработчики ----------
@router.callback_query(F.data == "cancel_writing")
async def cancel_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)

@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(WritingStates.choosing_type)
    await show_task_types(callback.message, edit=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_writing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)