import os
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from speaking.services.tts import text_to_voice
import redis.asyncio as redis

router = Router()
logger = logging.getLogger(__name__)

TASKS_FILE = "data/listening_tasks.json"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

with open(TASKS_FILE, "r", encoding="utf-8") as f:
    ALL_TASKS = json.load(f)

LEVELS = {
    "beginner": "🌱 Новичок",
    "intermediate": "🌟 Любитель",
    "expert": "🚀 Эксперт"
}

redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

class ListeningState(StatesGroup):
    choosing_level = State()
    answering_task = State()

# ---------- Клавиатуры ----------
def get_levels_keyboard():
    buttons = []
    for level, label in LEVELS.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"listening_level_{level}")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_task_keyboard(task_index):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Показать ответ", callback_data=f"listening_show_answer_{task_index}"),
            InlineKeyboardButton(text="Завершить", callback_data="listening_finish")
        ]
    ])

def get_continue_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Следующее задание", callback_data="listening_next_block")],
        [InlineKeyboardButton(text="Завершить сессию", callback_data="listening_finish_session")]
    ])

# ---------- Вспомогательные ----------
async def get_user_block_index(user_id: int, level: str) -> int:
    r = await get_redis()
    key = f"listening_progress:{user_id}:{level}"
    val = await r.get(key)
    return int(val) if val else 0

async def set_user_block_index(user_id: int, level: str, index: int):
    r = await get_redis()
    await r.set(f"listening_progress:{user_id}:{level}", str(index))

def get_blocks_by_level(level):
    return [b for b in ALL_TASKS if b["level"] == level]

def normalize_order_answer(answer: str) -> str:
    parts = [p.strip().upper() for p in answer.split(';') if p.strip()]
    return ';'.join(parts)

def normalize_text_answer(answer: str) -> str:
    return ' '.join(answer.strip().lower().split())

async def send_audio_and_start_tasks(message: Message, user_id: int, level: str, state: FSMContext):
    blocks = get_blocks_by_level(level)
    if not blocks:
        await message.answer("Заданий для этого уровня пока нет.")
        return
    block_index = await get_user_block_index(user_id, level)
    if block_index >= len(blocks):
        block_index = 0
    block = blocks[block_index]

    await state.update_data({
        "level": level,
        "block_index": block_index,
        "block": block,
        "task_index": 0,
        "correct": 0,
        "wrong": 0,
        "total": len(block["tasks"]),
        "answered": False
    })

    # Генерация аудио (используем тот же голос, что и в voice.py, без параметра speed)
    audio_path = await text_to_voice(block["text"], voice_id="yM93hbw8Qtvdma2wCnJG")
    if audio_path and os.path.exists(audio_path):
        try:
            with open(audio_path, 'rb') as f:
                audio_bytes = f.read()
            audio_file = BufferedInputFile(audio_bytes, filename="audio.mp3")
            await message.answer_audio(audio_file, caption="Прослушайте аудио, затем отвечайте на задания.")
            os.unlink(audio_path)
        except Exception as e:
            logger.error(f"Ошибка отправки аудио: {e}")
            await message.answer(f"Текст для прослушивания:\n\n{block['text']}")
    else:
        await message.answer(f"Текст для прослушивания:\n\n{block['text']}")

    # Отправляем первое задание
    await send_task(message, state)

async def send_task(message: Message, state: FSMContext, first: bool = True):
    data = await state.get_data()
    tasks = data["block"]["tasks"]
    task_index = data.get("task_index", 0)
    if task_index >= len(tasks):
        await finish_block(message, state)
        return

    task = tasks[task_index]
    await state.update_data({"current_task": task, "current_task_index": task_index, "answered": False})

    if task["type"] == "title":
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(task["options"])])
        text = f"Задание {task_index+1} из {len(tasks)}: Выберите заголовок для текста.\n\n{options_text}\n\nВведите номер правильного варианта (1, 2, 3...):"
    elif task["type"] == "open":
        text = f"Задание {task_index+1} из {len(tasks)}: {task['question']}\n\nВведите ваш ответ текстом:"
    elif task["type"] == "fill":
        fill_text = task["text"]
        text = f"Задание {task_index+1} из {len(tasks)}: Вставьте пропущенные слова.\n\n{fill_text}\n\nВведите все пропущенные слова через точку с запятой (;), например: ___; ___; ___;"
    elif task["type"] == "order":
        items = task["items"]
        formatted = "\n".join([f"{chr(65+i)}) {item}" for i, item in enumerate(items)])
        text = f"Задание {task_index+1} из {len(tasks)}: Расставьте события по порядку.\n\n{formatted}\n\nВведите буквы через точку с запятой (;), например: A; B; C"
    else:
        return

    keyboard = get_task_keyboard(task_index)
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(ListeningState.answering_task)

async def finish_block(message: Message, state: FSMContext):
    data = await state.get_data()
    correct = data.get("correct", 0)
    wrong = data.get("wrong", 0)
    total = data.get("total", 0)
    stats = f"Правильно: {correct}\nОшибок: {wrong}\nТочность: {correct/total*100:.1f}%" if total else "Вы не ответили ни на одно задание."

    level = data["level"]
    block_index = data["block_index"] + 1
    user_id = message.from_user.id
    blocks = get_blocks_by_level(level)
    if block_index >= len(blocks):
        block_index = 0
    await set_user_block_index(user_id, level, block_index)

    await message.answer(f"Блок завершён!\n\n{stats}", reply_markup=get_continue_keyboard())
    await state.clear()

# ---------- Хендлеры ----------
@router.callback_query(F.data == "start_listening")
@router.message(Command("listening"))
async def listening_start(event, state: FSMContext):
    await state.clear()
    text = "Учебный режим - <b>🎧 Аудирование</b>\nПрослушайте запись, прочитайте задания, затем напишите ответы через \";\"\n\nВыберите уровень:"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=get_levels_keyboard(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="HTML")
        await event.answer()

@router.callback_query(F.data.startswith("listening_level_"))
async def level_selected(callback: CallbackQuery, state: FSMContext):
    level = callback.data.split("_")[-1]
    user_id = callback.from_user.id
    await callback.message.delete()
    await send_audio_and_start_tasks(callback.message, user_id, level, state)
    await callback.answer()

# Универсальный обработчик для всех текстовых сообщений
@router.message(F.text)
async def handle_text_answer(message: Message, state: FSMContext):
    # Проверяем, находимся ли мы в режиме аудирования
    current_state = await state.get_state()
    if current_state != ListeningState.answering_task:
        return  # пропускаем, если не в аудировании

    data = await state.get_data()
    if data.get("answered", False):
        await message.answer("Вы уже ответили на это задание. Переходим к следующему.")
        data["task_index"] = data.get("task_index", 0) + 1
        await state.update_data(data)
        await send_task(message, state)
        return

    task = data.get("current_task")
    if not task:
        await message.answer("Ошибка. Попробуйте начать заново.")
        return

    user_input = message.text.strip()
    if not user_input:
        await message.answer("Пожалуйста, введите ответ.")
        return

    if task["type"] == "order":
        normalized = normalize_order_answer(user_input)
        correct = task["correct"]
        normalized_correct = normalize_order_answer(correct)
        is_correct = (normalized == normalized_correct)
        if is_correct:
            data["correct"] += 1
            result_text = "Правильно."
        else:
            data["wrong"] += 1
            result_text = f"Неправильно. Правильный порядок: {correct}"
    elif task["type"] == "title":
        correct = task["correct"]
        if correct.isdigit():
            is_correct = (user_input.strip() == correct)
            correct_answer = task["options"][int(correct)-1] if is_correct else task["options"][int(correct)-1]
        else:
            is_correct = normalize_text_answer(user_input) == normalize_text_answer(correct)
            correct_answer = correct
        if is_correct:
            data["correct"] += 1
            result_text = "Правильно."
        else:
            data["wrong"] += 1
            result_text = f"Неправильно. Правильный ответ: {correct_answer}"
    elif task["type"] == "fill":
        user_answers = [normalize_text_answer(a) for a in user_input.split(';') if a.strip()]
        correct_answers = [normalize_text_answer(a) for a in task["answers"]]
        if len(user_answers) != len(correct_answers):
            is_correct = False
            result_text = f"Неправильно. Количество ответов не совпадает. Ожидалось {len(correct_answers)} слов."
        else:
            all_correct = all(u == c for u, c in zip(user_answers, correct_answers))
            if all_correct:
                data["correct"] += 1
                result_text = "Правильно."
            else:
                data["wrong"] += 1
                correct_str = "; ".join(task["answers"])
                result_text = f"Неправильно. Правильные ответы: {correct_str}"
    else:  # open
        correct = task["correct"]
        variants = [normalize_text_answer(v) for v in correct.split(';')]
        user_ans = normalize_text_answer(user_input)
        is_correct = user_ans in variants
        if is_correct:
            data["correct"] += 1
            result_text = "Правильно."
        else:
            data["wrong"] += 1
            result_text = f"Неправильно. Правильный ответ: {correct}"

    await message.answer(result_text)
    data["answered"] = True
    await state.update_data(data)

    data["task_index"] = data.get("task_index", 0) + 1
    await state.update_data(data)
    await send_task(message, state)

# ---------- Обработчики кнопок ----------
@router.callback_query(F.data.startswith("listening_show_answer_"))
async def show_answer(callback: CallbackQuery, state: FSMContext):
    task_index = int(callback.data.split("_")[-1])
    data = await state.get_data()
    current_task_index = data.get("current_task_index")
    if current_task_index != task_index:
        await callback.answer("Это не текущее задание.", show_alert=True)
        return

    task = data.get("current_task")
    if not task:
        await callback.answer("Ошибка.", show_alert=True)
        return

    if task["type"] == "title":
        correct = task["correct"]
        if correct.isdigit():
            answer_text = task["options"][int(correct)-1]
        else:
            answer_text = correct
    elif task["type"] == "fill":
        answer_text = "; ".join(task["answers"])
    elif task["type"] == "order":
        answer_text = task["correct"]
    else:
        answer_text = task["correct"]

    await callback.message.answer(f"Правильный ответ: {answer_text}")
    data["answered"] = True
    await state.update_data(data)

    data["task_index"] = data.get("task_index", 0) + 1
    await state.update_data(data)
    await send_task(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "listening_finish")
async def finish_session(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Сессия завершена. Возвращаемся в меню выбора уровня.")
    text = "Учебный режим - <b>🎧 Аудирование</b>\nПрослушайте запись, прочитайте задания, затем напишите ответы через \";\"\n\nВыберите уровень:"
    await callback.message.answer(text, reply_markup=get_levels_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "listening_next_block")
async def next_block(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "Учебный режим - <b>🎧 Аудирование</b>\nПрослушайте запись, прочитайте задания, затем напишите ответы через \";\"\n\nВыберите уровень:"
    await callback.message.edit_text(text, reply_markup=get_levels_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "listening_finish_session")
async def finish_session_from_block(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Сессия аудирования завершена. Возвращаемся в главное меню.")
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from .start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()