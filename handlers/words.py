# handlers/words.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from data.users import get_user_state, set_user_state
from data.words_gold import WORDS_GOLD

router = Router()

# ----- FSM для добавления своего слова -----
class AddWordStates(StatesGroup):
    waiting_for_word = State()
    waiting_for_translation = State()
    waiting_for_example = State()

# ----- Вспомогательные функции для интервального повторения (SM-2) -----
def init_word_progress(user_id: int, word_id: str):
    state = get_user_state(user_id)
    if "words_progress" not in state:
        state["words_progress"] = {}
    if word_id not in state["words_progress"]:
        state["words_progress"][word_id] = {
            "interval": 1,
            "repetitions": 0,
            "ease_factor": 2.5,
            "next_review": None,
            "last_result": None
        }
        set_user_state(user_id, state)

def update_progress(user_id: int, word_id: str, quality: int):
    state = get_user_state(user_id)
    prog = state["words_progress"].get(word_id)
    if not prog:
        init_word_progress(user_id, word_id)
        prog = state["words_progress"][word_id]
    if quality >= 3:
        if prog["repetitions"] == 0:
            prog["interval"] = 1
        elif prog["repetitions"] == 1:
            prog["interval"] = 6
        else:
            prog["interval"] = round(prog["interval"] * prog["ease_factor"])
        prog["repetitions"] += 1
    else:
        prog["repetitions"] = 0
        prog["interval"] = 1
        prog["ease_factor"] = max(1.3, prog["ease_factor"] - 0.2)
    prog["last_result"] = quality
    set_user_state(user_id, state)

# ----- Клавиатуры -----
def get_categories_keyboard():
    buttons = []
    for cat_key, cat_data in WORDS_GOLD.items():
        buttons.append([InlineKeyboardButton(text=cat_data["name"], callback_data=f"word_cat_{cat_key}")])
    buttons.append([InlineKeyboardButton(text="📚 Мои слова", callback_data="word_my_words")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить слово", callback_data="word_add_start")])
    buttons.append([InlineKeyboardButton(text="📊 Статистика", callback_data="word_stats")])
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_word_card_keyboard(cat_key: str, word_index: int, total: int, word_id: str, is_my_words: bool = False):
    kb = [
        [InlineKeyboardButton(text="✅ Знаю", callback_data=f"word_known_{cat_key}_{word_index}_{word_id}"),
         InlineKeyboardButton(text="❌ Не знаю", callback_data=f"word_unknown_{cat_key}_{word_index}_{word_id}")],
        [InlineKeyboardButton(text="🔊 Детали", callback_data=f"word_details_{cat_key}_{word_index}_{word_id}")]
    ]
    nav_buttons = []
    if word_index > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"word_prev_{cat_key}_{word_index}_{word_id}"))
    if word_index < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"word_next_{cat_key}_{word_index}_{word_id}"))
    if nav_buttons:
        kb.append(nav_buttons)
    if is_my_words:
        kb.append([InlineKeyboardButton(text="🗑 Удалить из моих", callback_data=f"word_delete_my_{word_id}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="word_back_to_categories")])
    kb.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ----- Обработчики -----
@router.callback_query(lambda c: c.data == "start_words")
async def words_start(callback: CallbackQuery):
    await callback.message.edit_text(
        "📖 <b>Режим Words</b>\n\nВыберите категорию слов или воспользуйтесь личным словарём.",
        reply_markup=get_categories_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("word_cat_"))
async def show_category(callback: CallbackQuery):
    cat_key = callback.data.split("_")[2]
    category = WORDS_GOLD.get(cat_key)
    if not category:
        await callback.answer("Категория не найдена")
        return
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    state["current_word_cat"] = cat_key
    state["current_word_index"] = 0
    state["current_word_list"] = category["words"]
    set_user_state(user_id, state)
    await show_word_card(callback.message, user_id, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("word_my_words"))
async def show_my_words(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    my_words = state.get("my_words", [])
    if not my_words:
        await callback.message.edit_text(
            "📭 У вас пока нет своих слов. Добавьте их через кнопку «➕ Добавить слово».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить слово", callback_data="word_add_start")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="start_words")]
            ]),
            parse_mode="HTML"
        )
        await callback.answer()
        return
    state["current_word_cat"] = "my_words"
    state["current_word_index"] = 0
    state["current_word_list"] = my_words
    set_user_state(user_id, state)
    await show_word_card(callback.message, user_id, edit=True, is_my_words=True)
    await callback.answer()

async def show_word_card(message: Message, user_id: int, edit: bool = True, is_my_words: bool = False):
    state = get_user_state(user_id)
    word_list = state.get("current_word_list", [])
    idx = state.get("current_word_index", 0)
    if not word_list or idx >= len(word_list):
        await message.answer("Список слов пуст.")
        return
    word_obj = word_list[idx]
    word = word_obj["word"]
    trans = word_obj.get("trans", "")
    part_of_speech = word_obj.get("part_of_speech", "")
    definition = word_obj.get("definition", "")
    example = word_obj.get("example", "")
    collocations = word_obj.get("collocations", "")
    
    # Формируем текст карточки
    text = f"<b>{word}</b>"
    if trans:
        text += f" — {trans}"
    if part_of_speech:
        text += f" <i>({part_of_speech})</i>"
    text += "\n\n"
    if definition:
        text += f"📖 {definition}\n\n"
    if example:
        text += f"📝 {example}\n"
    if collocations:
        text += f"🔗 {collocations}\n"
    
    # Кнопки
    cat_key = state.get("current_word_cat", "unknown")
    total = len(word_list)
    word_id = f"{word}_{trans}" if trans else word
    keyboard = get_word_card_keyboard(cat_key, idx, total, word_id, is_my_words)
    
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(lambda c: c.data.startswith("word_known_"))
async def word_known(callback: CallbackQuery):
    _, _, cat_key, idx_str, word_id = callback.data.split("_")
    idx = int(idx_str)
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    if cat_key != "my_words":
        init_word_progress(user_id, word_id)
        update_progress(user_id, word_id, quality=3)
    word_list = state.get("current_word_list", [])
    if idx + 1 < len(word_list):
        state["current_word_index"] = idx + 1
        set_user_state(user_id, state)
        await show_word_card(callback.message, user_id, edit=True, is_my_words=(cat_key=="my_words"))
    else:
        await callback.message.edit_text("🎉 Вы прошли все слова в этой категории!")
        await callback.message.answer("Вернуться к категориям?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К категориям", callback_data="start_words")]
        ]))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("word_unknown_"))
async def word_unknown(callback: CallbackQuery):
    _, _, cat_key, idx_str, word_id = callback.data.split("_")
    idx = int(idx_str)
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    word_list = state.get("current_word_list", [])
    word_obj = word_list[idx]
    correct = f"{word_obj['word']} — {word_obj.get('trans', 'перевод отсутствует')}"
    if cat_key != "my_words":
        init_word_progress(user_id, word_id)
        update_progress(user_id, word_id, quality=0)
    if idx + 1 < len(word_list):
        state["current_word_index"] = idx + 1
        set_user_state(user_id, state)
        await callback.message.answer(f"❌ Правильный ответ: {correct}\n\nПереходим к следующему слову.")
        await show_word_card(callback.message, user_id, edit=True, is_my_words=(cat_key=="my_words"))
    else:
        await callback.message.answer(f"❌ Правильный ответ: {correct}\n\nЭто было последнее слово.")
        await callback.message.answer("Вернуться к категориям?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К категориям", callback_data="start_words")]
        ]))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("word_details_"))
async def word_details(callback: CallbackQuery):
    _, _, cat_key, idx_str, word_id = callback.data.split("_")
    idx = int(idx_str)
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    word_list = state.get("current_word_list", [])
    if idx >= len(word_list):
        await callback.answer("Слово не найдено")
        return
    w = word_list[idx]
    text = f"<b>{w['word']}</b>"
    if w.get("part_of_speech"):
        text += f" <i>({w['part_of_speech']})</i>"
    text += "\n\n"
    text += f"📖 Перевод: {w.get('trans', '—')}\n"
    if w.get("definition"):
        text += f"📚 Определение: {w['definition']}\n"
    if w.get("example"):
        text += f"📝 Пример: {w['example']}\n"
    if w.get("collocations"):
        text += f"🔗 Коллокации: {w['collocations']}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("word_next_"))
async def word_next(callback: CallbackQuery):
    _, _, cat_key, idx_str, word_id = callback.data.split("_")
    idx = int(idx_str)
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    word_list = state.get("current_word_list", [])
    if idx + 1 < len(word_list):
        state["current_word_index"] = idx + 1
        set_user_state(user_id, state)
        await show_word_card(callback.message, user_id, edit=True, is_my_words=(cat_key=="my_words"))
    else:
        await callback.answer("Это последнее слово")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("word_prev_"))
async def word_prev(callback: CallbackQuery):
    _, _, cat_key, idx_str, word_id = callback.data.split("_")
    idx = int(idx_str)
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    if idx > 0:
        state["current_word_index"] = idx - 1
        set_user_state(user_id, state)
        await show_word_card(callback.message, user_id, edit=True, is_my_words=(cat_key=="my_words"))
    else:
        await callback.answer("Это первое слово")
    await callback.answer()

@router.callback_query(lambda c: c.data == "word_add_start")
async def add_word_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "➕ <b>Добавить слово</b>\n\nПришлите слово (на английском):",
        parse_mode="HTML"
    )
    await state.set_state(AddWordStates.waiting_for_word)
    await callback.answer()

@router.message(AddWordStates.waiting_for_word)
async def add_word_word(message: Message, state: FSMContext):
    word = message.text.strip()
    if not word:
        await message.answer("Пожалуйста, введите слово.")
        return
    await state.update_data(word=word)
    await message.answer("Теперь пришлите перевод слова:")
    await state.set_state(AddWordStates.waiting_for_translation)

@router.message(AddWordStates.waiting_for_translation)
async def add_word_translation(message: Message, state: FSMContext):
    trans = message.text.strip()
    if not trans:
        await message.answer("Пожалуйста, введите перевод.")
        return
    await state.update_data(trans=trans)
    await message.answer("Пришлите пример использования (или отправьте «-», чтобы пропустить):")
    await state.set_state(AddWordStates.waiting_for_example)

@router.message(AddWordStates.waiting_for_example)
async def add_word_example(message: Message, state: FSMContext):
    example = message.text.strip()
    if example == "-":
        example = ""
    data = await state.get_data()
    word = data["word"]
    trans = data["trans"]
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if "my_words" not in user_state:
        user_state["my_words"] = []
    user_state["my_words"].append({
        "word": word,
        "trans": trans,
        "example": example,
        "part_of_speech": "",
        "definition": "",
        "collocations": ""
    })
    set_user_state(user_id, user_state)
    await message.answer(f"✅ Слово «{word}» добавлено в ваш личный словарь!")
    await state.clear()
    await words_start(message)  # возврат в меню слов

@router.callback_query(lambda c: c.data == "word_back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    await words_start(callback)

@router.callback_query(lambda c: c.data == "word_stats")
async def word_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    progress = user_state.get("words_progress", {})
    total_words = len(progress)
    if total_words == 0:
        text = "📊 Вы ещё не изучали слова. Начните с любой категории!"
    else:
        learned = sum(1 for p in progress.values() if p.get("repetitions", 0) > 2)
        text = f"📊 Ваша статистика:\n\nВсего слов в изучении: {total_words}\nВыучено (повторено ≥3 раз): {learned}"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_words")]
    ]))
    await callback.answer()