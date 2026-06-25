# handlers/practice_utils.py
import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from data.users import get_user_state, set_user_state
from handlers.profile import update_stats_after_practice

async def show_practice_task(message: Message, user_id: int, edit: bool = True):
    from data.users import get_user_state, set_user_state
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
        total_subtasks = practice.get("total_subtasks", 0)
        if total_subtasks == 0:
            tasks = practice.get("tasks", [])
            total_subtasks = sum(len(t.get("subtasks", [])) for t in tasks)
        wrong = total_subtasks - correct
        update_stats_after_practice(user_id, correct, wrong)

        current_variant = practice.get("variant_index", 0)
        lesson_content = user_state.get("current_lesson", {}).get("content", {})
        practice_bank = lesson_content.get("practice_bank", [])
        if practice_bank:
            next_variant = (current_variant + 1) % len(practice_bank)
            if "practice_variant" not in user_state:
                user_state["practice_variant"] = {}
            user_state["practice_variant"][lesson_key] = next_variant

        percent = int(correct / total_subtasks * 100) if total_subtasks else 0
        text = f"📊 Практика завершена!\nПравильно: {correct} из {total_subtasks} ({percent}%)\n\n"
        text += "🎉 Отлично!" if percent >= 80 else "📚 Повторите тему и попробуйте снова."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Вернуться к уроку", callback_data=f"back_to_lesson_{lesson_key}")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)
        user_state["practice_lesson_key"] = None
        set_user_state(user_id, user_state)
        return

    # --- ТЕКУЩЕЕ ЗАДАНИЕ ---
    task = tasks[task_idx]
    header = f"Задание {task_idx+1}/{len(tasks)}"

    # Берём описание задания (всё до первого пункта с номером)
    text_lines = task['text'].split('\n')
    description_lines = []
    for line in text_lines:
        if re.match(r'^\d+\.', line.strip()):
            break
        if line.strip() and not line.strip().startswith('Задание'):
            description_lines.append(line)

    description_text = '\n'.join(description_lines).strip()

    # Генерируем пункты из subtasks
    items_text = '\n'.join([f"{i+1}. {sub['question']}" for i, sub in enumerate(task['subtasks'])])

    instruction = "Введите все ответы через «;»"

    full_text = f"{header}\n{description_text}\n{instruction}\n\n{items_text}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data=f"practice_skip_{lesson_key}"),
         InlineKeyboardButton(text="Завершить", callback_data=f"practice_exit_{lesson_key}")]
    ])

    if edit:
        await message.edit_text(full_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(full_text, reply_markup=keyboard, parse_mode="HTML")