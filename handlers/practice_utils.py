# handlers/practice_utils.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from data.users import get_user_state, set_user_state
from handlers.profile import update_stats_after_practice

async def show_practice_task(message: Message, user_id: int, edit: bool = True):
    user_state = get_user_state(user_id)
    lesson_key = user_state.get("practice_lesson_key")
    if not lesson_key:
        await message.answer("Практика не активна")
        return
    
    practice = user_state.get("practice", {}).get(lesson_key)
    if not practice:
        await message.answer("Ошибка данных практики")
        return
    
    task_idx = practice.get("session_index", 0)
    tasks = practice.get("tasks", [])
    if task_idx >= len(tasks):
        correct = practice.get("session_correct", 0)
        total = len(tasks)
        wrong = total - correct
        update_stats_after_practice(user_id, correct, wrong)
        percent = int(correct/total*100) if total else 0
        text = f"📊 Практика завершена!\nПравильно: {correct} из {total} ({percent}%)\n\n"
        text += "🎉 Отлично!" if percent >= 80 else "📚 Повторите тему и попробуйте снова."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Вернуться к уроку", callback_data=f"back_to_lesson_{lesson_key}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)
        user_state["practice_lesson_key"] = None
        set_user_state(user_id, user_state)
        return
    
    task = tasks[task_idx]
    text = f"📝 {task['text']}\n\n"
    text += "Введите все ответы через запятую\n"
    progress = f"\nЗадание {task_idx+1} из {len(tasks)}. ✅ Правильных: {practice['session_correct']}"
    full_text = text + progress
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Подсказка", callback_data=f"practice_hint_{lesson_key}"),
         InlineKeyboardButton(text="⏩ Пропустить", callback_data=f"practice_skip_{lesson_key}")],
        [InlineKeyboardButton(text="❌ Завершить", callback_data=f"practice_exit_{lesson_key}"),
         InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    
    if edit:
        await message.edit_text(full_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(full_text, reply_markup=keyboard, parse_mode="HTML")