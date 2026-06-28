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
    "beginner": "Новичок",
    "intermediate": "Любитель",
    "expert": "Эксперт"
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
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_choices_keyboard(options, task_index, task_type="choice"):
    buttons = []
    if task_type == "truefalse":
        buttons.append([InlineKeyboardButton(text="Верно", callback_data=f"listening_answer_{task_index}_true")])
        buttons.append([InlineKeyboardButton(text="Неверно", callback_data=f"listening_answer_{task_index}_false")])
    else:
        for i, opt in enumerate(options):
            buttons.append([InlineKeyboardButton(text=opt, callback_data=f"listening_answer_{task_index}_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_repeat_audio_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Повторить аудио", callback_data="listening_repeat_audio")]
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
        "total": len(block["tasks"])
    })

    # Генерируем аудио
    audio_path = await text_to_voice(block["text"], voice_id="yM93hbw8Qtvdma2wCnJG")
    if audio_path and os.path.exists(audio_path):
        try:
            with open(audio_path, 'rb') as f:
                audio_bytes = f.read()
            audio_file = BufferedInputFile(audio_bytes, filename="audio.mp3")
            await message.answer_audio(audio_file, caption="🎧 Прослушайте аудио, затем отвечайте на задания.", reply_markup=get_repeat_audio_keyboard())
            os.unlink(audio_path)
        except Exception as e:
            logger.error(f"Ошибка отправки аудио: {e}")
            await message.answer(f"🎧 Текст для прослушивания:\n\n{block['text']}", reply_markup=get_repeat_audio_keyboard())
    else:
        await message.answer(f"🎧 Текст для прослушивания:\n\n{block['text']}", reply_markup=get_repeat_audio_keyboard())

    # Показываем первое задание
    await send_task(message, state, first=True)

async def send_task(message: Message, state: FSMContext, first: bool = False):
    data = await state.get_data()
    tasks = data["block"]["tasks"]
    task_index = data.get("task_index", 0)
    if task_index >= len(tasks):
        await finish_block(message, state)
        return

    task = tasks[task_index]
    await state.update_data({"current_task": task, "current_task_index": task_index})

    if task["type"] == "title":
        text = f"📌 Задание {task_index+1} из {len(tasks)}: Выберите заголовок для текста:"
        keyboard = get_choices_keyboard(task["options"], task_index, "choice")
    elif task["type"] == "truefalse":
        text = f"📌 Задание {task_index+1} из {len(tasks)}: Верно ли утверждение?\n\n{task['statement']}"
        keyboard = get_choices_keyboard([], task_index, "truefalse")
    elif task["type"] == "choice":
        text = f"📌 Задание {task_index+1} из {len(tasks)}: {task['question']}"
        keyboard = get_choices_keyboard(task["options"], task_index, "choice")
    elif task["type"] == "order":
        items = task["items"]
        formatted = "\n".join([f"{chr(65+i)}) {item}" for i, item in enumerate(items)])
        text = f"📌 Задание {task_index+1} из {len(tasks)}: Расставьте события по порядку.\nВведите буквы через точку с запятой (;), например: A; B; C\n\n{formatted}"
        keyboard = None
    else:
        return

    if first:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    await state.set_state(ListeningState.answering_task)

async def finish_block(message: Message, state: FSMContext):
    data = await state.get_data()
    correct = data.get("correct", 0)
    wrong = data.get("wrong", 0)
    total = data.get("total", 0)
    stats = f"✅ Правильно: {correct}\n❌ Ошибок: {wrong}\n📊 Точность: {correct/total*100:.1f}%" if total else "Вы не ответили ни на одно задание."

    level = data["level"]
    block_index = data["block_index"] + 1
    user_id = message.from_user.id
    blocks = get_blocks_by_level(level)
    if block_index >= len(blocks):
        block_index = 0
    await set_user_block_index(user_id, level, block_index)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Следующее задание", callback_data="listening_next_block")],
        [InlineKeyboardButton(text="Завершить сессию", callback_data="listening_finish")]
    ])
    await message.answer(f"📋 Блок завершён!\n\n{stats}", reply_markup=keyboard)
    await state.clear()

# ---------- Хендлеры ----------
@router.callback_query(F.data == "start_listening")
@router.message(Command("listening"))
async def listening_start(event, state: FSMContext):
    await state.clear()
    # Отладочное сообщение для проверки, что колбэк сработал
    if isinstance(event, CallbackQuery):
        await event.answer("✅ Кнопка сработала!", show_alert=True)
    text = "🎧 Аудирование\nУчебный режим - Аудирование.\nПрослушайте запись, затем напишите ответы через \";\"\nВыберите уровень:"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=get_levels_keyboard())
    else:
        await event.message.edit_text(text, reply_markup=get_levels_keyboard())
        # Не вызываем callback.answer() повторно, уже вызвали выше
        # await event.answer() # закомментировать, чтобы не было двойного ответа

@router.callback_query(F.data.startswith("listening_level_"))
async def level_selected(callback: CallbackQuery, state: FSMContext):
    level = callback.data.split("_")[-1]
    user_id = callback.from_user.id
    await callback.message.delete()
    await send_audio_and_start_tasks(callback.message, user_id, level, state)
    await callback.answer()

@router.callback_query(F.data.startswith("listening_answer_"))
async def handle_button_answer(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_index = data.get("current_task_index")
    task = data.get("current_task")
    if not task:
        await callback.answer("Ошибка, начните заново.")
        return

    parts = callback.data.split("_")
    if task["type"] == "truefalse":
        user_answer = parts[-1] == "true"
        correct = task["correct"]
        is_correct = (user_answer == correct)
    else:
        selected_index = int(parts[-1])
        correct_index = task["correct"]
        is_correct = (selected_index == correct_index)
        correct_answer = task["options"][correct_index] if "options" in task else ""

    if is_correct:
        data["correct"] += 1
        result_text = "✅ Правильно!"
    else:
        data["wrong"] += 1
        if task["type"] == "truefalse":
            result_text = f"❌ Неправильно. Правильно: {'Верно' if correct else 'Неверно'}"
        else:
            result_text = f"❌ Неправильно. Правильный ответ: {correct_answer}"

    await callback.message.edit_text(f"{result_text}\n\n{callback.message.text}")
    await state.update_data(data)

    data["task_index"] = data.get("task_index", 0) + 1
    await state.update_data(data)
    await send_task(callback.message, state, first=False)
    await callback.answer()

@router.message(ListeningState.answering_task, F.text)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    task = data.get("current_task")
    if not task or task["type"] != "order":
        await message.answer("Сейчас не ожидается текстовый ответ.")
        return

    user_input = message.text.strip()
    normalized = normalize_order_answer(user_input)
    correct = task["correct"]
    normalized_correct = normalize_order_answer(correct)

    is_correct = (normalized == normalized_correct)
    if is_correct:
        data["correct"] += 1
        result_text = "✅ Правильно!"
    else:
        data["wrong"] += 1
        result_text = f"❌ Неправильно. Правильный порядок: {correct}"

    await message.answer(result_text)
    await state.update_data(data)

    data["task_index"] = data.get("task_index", 0) + 1
    await state.update_data(data)
    await send_task(message, state, first=False)

@router.callback_query(F.data == "listening_repeat_audio")
async def repeat_audio(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    block = data.get("block")
    if not block:
        await callback.answer("Нет аудио для повторения.")
        return
    audio_path = await text_to_voice(block["text"], voice_id="yM93hbw8Qtvdma2wCnJG")
    if audio_path and os.path.exists(audio_path):
        try:
            with open(audio_path, 'rb') as f:
                audio_bytes = f.read()
            audio_file = BufferedInputFile(audio_bytes, filename="audio.mp3")
            await callback.message.answer_audio(audio_file, caption="🔄 Повтор аудио")
            os.unlink(audio_path)
        except Exception as e:
            logger.error(f"Ошибка повторного аудио: {e}")
            await callback.message.answer(f"🔄 Текст для повторения:\n\n{block['text']}")
    else:
        await callback.message.answer(f"🔄 Текст для повторения:\n\n{block['text']}")
    await callback.answer()

@router.callback_query(F.data == "listening_next_block")
async def next_block(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите уровень сложности:", reply_markup=get_levels_keyboard())
    await callback.answer()

@router.callback_query(F.data == "listening_finish")
async def finish_listening(callback: CallbackQuery, state: FSMContext):
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