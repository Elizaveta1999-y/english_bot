import re
import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from data.users import get_user_state, set_user_state
from services.deepseek import chat
from speaking.services.ai import process_roleplay_message

logger = logging.getLogger(__name__)
router = Router()

class RoleplayStates(StatesGroup):
    active = State()

# ---------- КАТЕГОРИИ (только названия на английском) ----------
CATEGORIES = [
    ("💼 Work & Business", "work"),
    ("✈️ Travel", "travel"),
    ("🏠 Daily Life", "daily"),
    ("💪 Health & Fitness", "health"),
    ("👨‍👩‍👧 Family & Home", "family"),
    ("📱 Technology", "tech"),
    ("💅 Beauty Routine", "beauty"),
    ("🛍️ Shopping & Dining", "shopping"),
    ("🗣️ Small Talk", "small_talk")
]

# ---------- ТЕМЫ (всё на русском) ----------
TOPICS = {
    "work": [
        {
            "name": "Собеседование на работу",
            "description": "Вы проходите собеседование в IT-компанию. HR задаёт вопросы о вашем опыте и навыках.",
            "goals": ["Расскажите о своём последнем месте работы", "Опишите свои сильные стороны", "Объясните, почему хотите работать именно здесь"]
        },
        {
            "name": "Переговоры с клиентом",
            "description": "Вы обсуждаете условия поставки с потенциальным клиентом. Он хочет скидку.",
            "goals": ["Представьте своё коммерческое предложение", "Ответьте на возражения о цене", "Договоритесь о взаимовыгодных условиях"]
        },
        {
            "name": "Презентация проекта",
            "description": "Вы показываете новый проект руководству. Нужно кратко и ясно изложить суть.",
            "goals": ["Опишите проблему, которую решает проект", "Перечислите ключевые преимущества", "Ответьте на вопросы коллег"]
        },
        {
            "name": "Разговор с начальником о повышении",
            "description": "Вы просите о повышении зарплаты или продвижении по службе.",
            "goals": ["Чётко сформулируйте свою просьбу", "Приведите аргументы (достижения, результаты)", "Предложите компромиссный вариант"]
        },
        {
            "name": "Ежедневный планер",
            "description": "Утреннее совещание: вы обсуждаете задачи на день с руководителем.",
            "goals": ["Перечислите запланированные задачи", "Уточните приоритеты на сегодня", "Согласуйте дедлайны"]
        },
        {
            "name": "Оценка производительности",
            "description": "Годовой обзор: вы обсуждаете свои успехи и планы на следующий год.",
            "goals": ["Оцените свои достижения за год", "Укажите зоны для роста", "Поставьте цели на будущий год"]
        }
    ],
    "travel": [
        {
            "name": "Бронирование отеля",
            "description": "Вы звоните в отель, чтобы забронировать номер на даты отпуска.",
            "goals": ["Уточните наличие номеров", "Назовите даты заезда и выезда", "Узнайте цену и условия бронирования"]
        },
        {
            "name": "Ранний заезд",
            "description": "Вы приехали раньше времени и просите заселить вас сейчас, а не в 14:00.",
            "goals": ["Объясните ситуацию (ранний рейс)", "Спросите, есть ли свободный номер", "Договоритесь о доплате или бесплатном раннем заезде"]
        },
        {
            "name": "Проблема с номером (не работает кондиционер)",
            "description": "Вы звоните на ресепшн и сообщаете, что в номере не работает кондиционер.",
            "goals": ["Опишите проблему", "Попросите прислать мастера", "Узнайте время решения"]
        },
        {
            "name": "Заказ такси до аэропорта",
            "description": "Вы просите администратора отеля вызвать такси к определённому времени.",
            "goals": ["Сообщите время отправления", "Уточните стоимость поездки", "Спросите, можно ли оплатить картой"]
        },
        {
            "name": "Выбор экскурсии",
            "description": "Вы на ресепшн спрашиваете о доступных экскурсиях и ценах.",
            "goals": ["Узнайте, какие экскурсии предлагаются", "Спросите о длительности и стоимости", "Забронируйте место на завтра"]
        },
        {
            "name": "Поздний выезд (late check‑out)",
            "description": "Вы хотите продлить номер до вечера, потому что рейс поздно вечером.",
            "goals": ["Объясните причину", "Узнайте, возможен ли поздний выезд", "Договоритесь о доплате, если требуется"]
        }
    ],
    "daily": [
        {
            "name": "Вызов сантехника",
            "description": "У вас сломалась раковина на кухне. Вы звоните в управляющую компанию и вызываете мастера.",
            "goals": ["Опишите поломку", "Уточните время прихода мастера", "Оставьте свой номер и адрес"]
        },
        {
            "name": "Разговор с соседом о шуме",
            "description": "Соседи сверху громко слушают музыку поздно вечером. Вы поднимаетесь и вежливо просите сделать тише.",
            "goals": ["Поздоровайтесь и представьтесь", "Объясните, что вам мешает шум", "Попросите убавить звук и договоритесь о времени"]
        },
        {
            "name": "Покупка краски для стен в строительном магазине",
            "description": "Вы пришли в магазин и хотите купить краску для ванной. Консультант помогает с выбором.",
            "goals": ["Объясните, для какого помещения нужна краска", "Спросите о типах краски (влагостойкая, матовая и т.п.)", "Выберите цвет и объём"]
        },
        {
            "name": "Обсуждение перестановки с партнёром",
            "description": "Вы с партнёром решаете, как переставить мебель в гостиной, и у вас разные мнения.",
            "goals": ["Предложите свой вариант расстановки", "Выслушайте мнение партнёра", "Придите к компромиссу"]
        },
        {
            "name": "Возврат бракованного товара",
            "description": "Вы купили наушники, но они сломались через два дня. Вы приходите в магазин и просите вернуть деньги.",
            "goals": ["Объясните причину возврата (брак)", "Предъявите чек или гарантийный талон", "Добейтесь возврата денег или обмена"]
        },
        {
            "name": "Запись в школу для ребёнка",
            "description": "Вы звоните в ближайшую школу, чтобы записать ребёнка в первый класс.",
            "goals": ["Узнайте, идёт ли приём заявлений", "Спросите список документов", "Запишитесь на собеседование"]
        }
    ],
    "health": [
        {
            "name": "Запись к терапевту",
            "description": "Вы звоните в поликлинику, чтобы записаться к терапевту на завтра.",
            "goals": ["Назовите свои данные (ФИО, полис)", "Опишите симптомы кратко", "Договоритесь о времени приёма"]
        },
        {
            "name": "Консультация по симптомам",
            "description": "Вы звоните в справочную службу и описываете свои симптомы, чтобы узнать, к какому врачу идти.",
            "goals": ["Чётко опишите симптомы", "Уточните, когда они начались", "Получите рекомендацию по специалисту"]
        },
        {
            "name": "Покупка аналога лекарства",
            "description": "В аптеке вам говорят, что нужного препарата нет. Вы просите посоветовать аналог подешевле.",
            "goals": ["Назовите оригинальный препарат", "Спросите, есть ли дженерик", "Сравните состав и цену"]
        },
        {
            "name": "Получение результатов анализов",
            "description": "Вы звоните в лабораторию, чтобы узнать результаты своих анализов.",
            "goals": ["Назовите номер заказа и свои данные", "Попросите продиктовать результаты", "Уточните, есть ли отклонения от нормы"]
        },
        {
            "name": "Вопрос о прививке от гриппа",
            "description": "Вы хотите сделать прививку и звоните в прививочный кабинет, чтобы узнать о противопоказаниях.",
            "goals": ["Узнайте, есть ли противопоказания", "Спросите, можно ли делать прививку при простуде", "Запишитесь на процедуру"]
        },
        {
            "name": "Консультация в фитнес-клубе",
            "description": "Вы приходите в спортзал и хотите взять персональные тренировки. Тренер расспрашивает о ваших целях.",
            "goals": ["Расскажите о своей физической форме", "Объясните, чего хотите достичь (похудеть, накачаться)", "Задайте вопросы о программе и цене"]
        }
    ],
    "family": [
        {
            "name": "Поздравление с днём рождения",
            "description": "Вы звоните бабушке, чтобы поздравить её с днём рождения. Вы не можете приехать, поэтому объясняете причину.",
            "goals": ["Искренне поздравьте", "Объясните, почему не сможете приехать (работа, учёба)", "Пообещайте приехать позже"]
        },
        {
            "name": "Обсуждение отпуска с семьёй",
            "description": "Вы с супругом обсуждаете, куда поехать в отпуск. У вас разные предпочтения (море или горы).",
            "goals": ["Выскажите свои пожелания", "Выслушайте аргументы партнёра", "Придите к общему решению"]
        },
        {
            "name": "Разговор с подростком об оценках",
            "description": "Вы — родитель, у ребёнка плохие оценки в школе. Вы обсуждаете, как исправить ситуацию.",
            "goals": ["Обсудите причины плохих оценок", "Предложите план действий (репетитор, дополнительные занятия)", "Договоритесь о контроле"]
        },
        {
            "name": "Поддержка друга в трудной ситуации",
            "description": "Ваш друг расстроен из‑за проблем на работе. Вы хотите его утешить и поддержать.",
            "goals": ["Выразите сочувствие", "Предложите помощь или совет", "Постарайтесь поднять настроение"]
        },
        {
            "name": "Запись ребёнка в кружок",
            "description": "Вы звоните в детский центр, чтобы записать ребёнка на занятия по робототехнике.",
            "goals": ["Уточните возрастную группу", "Спросите расписание и стоимость", "Запишите ребёнка на пробное занятие"]
        }
    ],
    "tech": [
        {
            "name": "Проблемы с интернетом",
            "description": "У вас пропал Wi‑Fi. Вы звоните провайдеру в техподдержку.",
            "goals": ["Опишите проблему (нет света на роутере, ошибка)", "Сообщите свой номер договора", "Узнайте, когда приедет мастер"]
        },
        {
            "name": "Восстановление пароля от почты",
            "description": "Вы забыли пароль от электронной почты и звоните в службу поддержки, чтобы восстановить доступ.",
            "goals": ["Назовите свою почту", "Ответьте на контрольные вопросы", "Получите ссылку для сброса пароля"]
        },
        {
            "name": "Настройка нового телефона",
            "description": "Вы купили новый смартфон и звоните в поддержку, чтобы перенести данные со старого.",
            "goals": ["Спросите, как перенести контакты и фото", "Уточните, нужна ли синхронизация с облаком", "Выполните инструкции"]
        },
        {
            "name": "Отмена подписки на стриминг",
            "description": "Вы хотите отменить платную подписку на Netflix и звоните в поддержку.",
            "goals": ["Объясните причину отмены", "Узнайте, нужно ли подтверждать по электронной почте", "Добейтесь отмены и подтверждения"]
        },
        {
            "name": "Проблема с заказом в приложении доставки",
            "description": "Вы заказали еду в приложении, но курьер не приехал. Вы звоните в поддержку.",
            "goals": ["Назовите номер заказа", "Опишите ситуацию (опоздание, неверный адрес)", "Узнайте статус заказа и попросите решение"]
        },
        {
            "name": "Регистрация на госуслугах",
            "description": "Вы пытаетесь зарегистрироваться на портале госуслуг, но не получается. Звоните в техподдержку.",
            "goals": ["Объясните, на каком этапе ошибка", "Следуйте инструкциям оператора", "Завершите регистрацию"]
        }
    ],
    "beauty": [
        {
            "name": "Запись на маникюр",
            "description": "Вы звоните в салон, чтобы записаться на маникюр в удобное время.",
            "goals": ["Уточните свободные слоты", "Спросите цену и какие услуги входят", "Запишитесь на конкретное время"]
        },
        {
            "name": "Выбор дизайна ногтей",
            "description": "Вы пришли к мастеру, показываете фото дизайна и обсуждаете, можно ли его сделать.",
            "goals": ["Объясните, какой дизайн хотите", "Уточните, можно ли его реализовать с вашей формой ногтей", "Согласуйте финальный вариант"]
        },
        {
            "name": "Наращивание ресниц",
            "description": "Вы хотите сделать наращивание ресниц, но боитесь аллергии. Вы обсуждаете это с мастером.",
            "goals": ["Спросите о противопоказаниях", "Уточните, какой материал используется", "Примите решение о процедуре"]
        },
        {
            "name": "Покупка косметики",
            "description": "Вы в магазине косметики, консультант помогает подобрать тональный крем под ваш тип кожи.",
            "goals": ["Расскажите о своём типе кожи", "Спросите о составе и стойкости", "Выберите подходящий продукт"]
        },
        {
            "name": "Возврат шампуня",
            "description": "Вы купили шампунь, но он вызвал раздражение. Вы приходите в магазин, чтобы его вернуть.",
            "goals": ["Объясните причину возврата (аллергия)", "Предъявите чек", "Оформите возврат или обмен"]
        },
        {
            "name": "Запись на коррекцию бровей",
            "description": "Вы звоните в brow‑студию, чтобы записаться на коррекцию и окрашивание бровей.",
            "goals": ["Уточните свободное время", "Спросите стоимость", "Запишитесь на процедуру"]
        }
    ],
    "shopping": [
        {
            "name": "Выбор джинсов в примерочной",
            "description": "Вы в магазине одежды, продавец приносит вам разные размеры и модели. Вы решаете, какие взять.",
            "goals": ["Скажите свой размер", "Примерьте и дайте обратную связь", "Выберите и купите подходящую пару"]
        },
        {
            "name": "Обмен подарка",
            "description": "Вам подарили свитер, но он мал. Вы приходите в магазин и просите обменять на другой размер.",
            "goals": ["Объясните ситуацию (подарок)", "Попросите обменять на нужный размер", "Если нет размера, выберите другую модель"]
        },
        {
            "name": "Заказ товара онлайн с доставкой",
            "description": "Вы звоните в службу поддержки интернет-магазина, чтобы уточнить статус заказа.",
            "goals": ["Назовите номер заказа", "Узнайте дату доставки", "Уточните, можно ли изменить адрес доставки"]
        },
        {
            "name": "Покупка бытовой техники",
            "description": "Вы выбираете пылесос, консультант в магазине помогает сравнить модели.",
            "goals": ["Расскажите, для каких целей нужен пылесос", "Сравните характеристики (мощность, тип фильтра)", "Примите решение о покупке"]
        },
        {
            "name": "Применение скидки по карте",
            "description": "Вы в супермаркете, хотите использовать накопительную скидку. Кассир проверяет карту.",
            "goals": ["Предъявите карту или назовите номер", "Уточните, действует ли скидка на ваш товар", "Оплатите покупку со скидкой"]
        },
        {
            "name": "Бронирование столика в ресторане",
            "description": "Вы звоните в ресторан, чтобы заказать столик на вечер пятницы.",
            "goals": ["Назовите количество человек", "Выберите время (например, 19:00)", "Уточните, есть ли дресс-код или предоплата"]
        },
        {
            "name": "Жалоба на счёт в кафе",
            "description": "Вам принесли счёт, но вы не заказывали один из напитков. Вы говорите об этом официанту.",
            "goals": ["Укажите лишнюю позицию", "Попросите исправить счёт", "Оплатите только то, что заказывали"]
        },
        {
            "name": "Рекомендация вина (сомелье)",
            "description": "Вы в ресторане, просите сомелье подобрать вино к мясному блюду.",
            "goals": ["Опишите своё блюдо", "Спросите рекомендации", "Выберите подходящее вино"]
        }
    ],
    "small_talk": [
        {
            "name": "Small Talk с коллегой у кулера",
            "description": "Вы встречаете коллегу в комнате отдыха и непринуждённо болтаете о выходных или погоде.",
            "goals": ["Начните лёгкий разговор", "Спросите о планах на выходные", "Расскажите что-то о себе"]
        },
        {
            "name": "Разговор с другим родителем на детской площадке",
            "description": "Вы начинаете беседу с незнакомым родителем, пока дети играют.",
            "goals": ["Представьтесь", "Поговорите о детях", "Обсудите район или предстоящие события"]
        },
        {
            "name": "Неформальная беседа перед собеседованием",
            "description": "Вы пришли на собеседование, и рекрутер предлагает кофе и заводит лёгкий разговор.",
            "goals": ["Вежливо ответьте о дороге", "Прокомментируйте погоду или офис", "Произведите хорошее первое впечатление"]
        },
        {
            "name": "Разговор с соседом в лифте",
            "description": "Вы встречаете соседа в лифте и обмениваетесь парой слов о доме или новостях.",
            "goals": ["Тепло поприветствуйте", "Скажите что-то нейтральное (ремонт, погода)", "Завершите разговор естественно"]
        },
        {
            "name": "На вечеринке – знакомство с новыми людьми",
            "description": "Вы на вечеринке и хотите начать разговор с незнакомым человеком.",
            "goals": ["Представьтесь", "Спросите, как они связаны с хозяином", "Найдите общие интересы"]
        }
    ]
}

# ---------- ВХОД В РОЛЕВУЮ ИГРУ ----------
@router.callback_query(F.data == "start_roleplay")
async def start_roleplay(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES
    ])
    await callback.message.answer(
        "🎭 Выберите категорию для ролевой игры:",
        reply_markup=keyboard
    )
    await callback.answer()

# ---------- ПОКАЗ ТЕМ С ПАГИНАЦИЕЙ ----------
@router.callback_query(F.data.startswith("cat_"))
async def show_topics(callback: CallbackQuery, page: int = 0):
    cat_id = callback.data[4:]
    topics_list = TOPICS.get(cat_id, [])
    if not topics_list:
        await callback.answer("В этой категории нет тем", show_alert=True)
        return

    ITEMS_PER_PAGE = 4
    total = len(topics_list)
    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1

    start = page * ITEMS_PER_PAGE
    end = min(start + ITEMS_PER_PAGE, total)
    page_topics = topics_list[start:end]

    buttons = []
    for idx, topic_info in enumerate(page_topics, start=start):
        buttons.append([InlineKeyboardButton(
            text=topic_info["name"],
            callback_data=f"topic_{cat_id}_{idx}_{page}"
        )])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"cat_page_{cat_id}_{page-1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"cat_page_{cat_id}_{page+1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="back_to_rp_categories")])

    topics_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    cat_display = next((c[0] for c in CATEGORIES if c[1] == cat_id), cat_id)
    await callback.message.edit_text(
        f"🎭 <b>{cat_display}</b>\n\nВыберите тему (страница {page+1}/{total_pages}):",
        reply_markup=topics_keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cat_page_"))
async def change_topic_page(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка")
        return
    cat_id = parts[2]
    page = int(parts[3])
    await show_topics(callback, page=page)

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer("")

# ---------- ВЫБОР КОНКРЕТНОЙ ТЕМЫ ----------
@router.callback_query(F.data.startswith("topic_"))
async def topic_chosen(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    cat_id = parts[1]
    idx = int(parts[2])

    topics_list = TOPICS.get(cat_id, [])
    if idx >= len(topics_list):
        await callback.answer("Тема не найдена", show_alert=True)
        return
    topic_info = topics_list[idx]
    topic = topic_info["name"]
    description = topic_info["description"]
    goals = topic_info["goals"]

    user_id = callback.from_user.id

    set_user_state(user_id, {
        "mode": "roleplay_active",
        "history": [],
        "roleplay_topic": topic,
        "roleplay_category": cat_id,
        "roleplay_custom_scenario": None,
        "awaiting_custom_scenario": False
    })

    await state.set_state(RoleplayStates.active)
    await callback.answer(f"Выбрана тема: {topic}")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Что ответить?"), KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Завершить диалог")]
        ],
        resize_keyboard=True
    )
    goals_text = "\n".join([f"{i+1}) {goal}" for i, goal in enumerate(goals)])
    roleplay_info = (
        f"🎭 <b>Ролевая игра: {topic}</b>\n\n"
        f"📖 Ситуация: {description}\n\n"
        f"🎯 Ваши цели:\n{goals_text}\n\n"
        f"🗣️ <b>Говорите голосом или пишите текстом.</b>\n"
        f"💡 Если нужна подсказка, нажмите «💡 Что ответить?».\n"
        f"Когда закончите, нажмите «📊 Завершить диалог» для анализа."
    )
    await callback.message.edit_text(roleplay_info, parse_mode="HTML")
    await callback.message.answer("🎬 <b>Можете начинать!</b>", reply_markup=keyboard, parse_mode="HTML")

# ---------- ВОЗВРАТ К КАТЕГОРИЯМ ----------
@router.callback_query(F.data == "back_to_rp_categories")
async def back_to_rp_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat[0], callback_data=f"cat_{cat[1]}")] for cat in CATEGORIES
    ])
    await callback.message.edit_text(
        "🎭 Выберите категорию для ролевой игры:",
        reply_markup=keyboard
    )
    await callback.answer()

# ---------- ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ В АКТИВНОЙ ИГРЕ ----------
@router.message(RoleplayStates.active, F.text)
async def handle_roleplay_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("mode") != "roleplay_active":
        return

    user_text = message.text
    try:
        ai_response = await process_roleplay_message(user_id, user_text)
    except Exception as e:
        logger.error(f"Ошибка в ролевой игре: {e}")
        await message.answer("Произошла ошибка. Попробуйте ещё раз.")
        return

    history = user_state.get("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": ai_response})
    if len(history) > 20:
        history = history[-20:]
    user_state["history"] = history
    set_user_state(user_id, user_state)

    await message.answer(ai_response)

# ---------- КНОПКА "💡 Что ответить?" ----------
@router.message(RoleplayStates.active, F.text == "💡 Что ответить?")
async def give_hint(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("history", [])
    last_bot_msg = None
    if history and history[-1].get("role") == "assistant":
        last_bot_msg = history[-1].get("text", "")
    prompt = (
        "Ты – помощник в ролевой игре. Пользователь просит подсказку, что можно ответить дальше.\n"
        f"Контекст диалога (последние сообщения):\n{history[-5:] if history else 'Нет истории'}\n"
        f"Последнее сообщение бота: {last_bot_msg or 'Нет сообщения'}\n"
        "Предложи 2–3 варианта того, что пользователь может сказать или спросить в этой ситуации.\n"
        "Ответы должны быть на русском, естественные, соответствовать роли и ситуации."
    )
    try:
        hint = await chat(prompt, max_tokens=200, temperature=0.7)
    except Exception as e:
        logger.error(f"Ошибка получения подсказки: {e}")
        await message.answer("Не удалось получить подсказку. Попробуйте позже.")
        return
    await message.answer(f"💡 <b>Идеи для ответа:</b>\n\n{hint}", parse_mode="HTML")

# ---------- КНОПКА "🏠 Главное меню" ----------
@router.message(RoleplayStates.active, F.text == "🏠 Главное меню")
async def exit_to_main_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    user_state["mode"] = ""
    user_state["history"] = []
    set_user_state(user_id, user_state)
    await state.clear()
    from handlers.start import show_main_menu
    await show_main_menu(message, edit=False)

# ---------- КНОПКА "📊 Завершить диалог" ----------
@router.message(RoleplayStates.active, F.text == "📊 Завершить диалог")
async def finish_roleplay(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    history = user_state.get("history", [])
    if not history:
        await message.answer("Вы пока ничего не сказали. Начните разговор!", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return

    history_text = "\n".join([f"{msg['role']}: {msg['text']}" for msg in history if msg['role'] in ['user', 'assistant']])
    prompt = (
        "Ты – языковой тренер. Проанализируй диалог пользователя с ИИ в ролевой игре и дай краткий фидбек:\n"
        "- Грамматика (2-3 основные ошибки с исправлениями)\n"
        "- Лексика (удачные фразы, что можно улучшить)\n"
        "- Достижение целей (насколько пользователь справился с задачей)\n"
        "Будь конструктивным, обращайся на 'ты'.\n\n"
        f"Диалог:\n{history_text}"
    )
    try:
        feedback = await chat(prompt, max_tokens=400, temperature=0.5)
    except Exception as e:
        logger.error(f"Ошибка получения фидбека: {e}")
        await message.answer("Не удалось получить фидбек. Попробуйте позже.")
        return

    user_state["mode"] = ""
    user_state["history"] = []
    set_user_state(user_id, user_state)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Начать новую игру", callback_data="start_roleplay")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await message.answer(f"📊 <b>Фидбек по диалогу:</b>\n\n{feedback}", reply_markup=keyboard, parse_mode="HTML")
    await message.answer("Ролевая игра завершена.", reply_markup=ReplyKeyboardRemove())