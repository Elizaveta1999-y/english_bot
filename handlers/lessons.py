# handlers/lessons.py
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, Message
from data.users import get_user_state, set_user_state
from data.level_a1 import LEVEL_A1_CONTENT
from data.level_a2 import LEVEL_A2_CONTENT
from data.level_b1 import LEVEL_B1_CONTENT
from data.level_b2 import LEVEL_B2_CONTENT
from data.level_c1 import LEVEL_C1_CONTENT
from data.level_c2 import LEVEL_C2_CONTENT
from data.thematic_new import THEMATIC_NEW_CONTENT
from services.deepseek import chat
from speaking.services.tts import text_to_voice
from handlers.profile import update_stats_after_lesson, update_stats_after_practice
from .practice_utils import show_practice_task

router = Router()

# ========== ОБЩАЯ ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ВОПРОСОВ ПО УРОКАМ ==========

async def process_lesson_question(user_id: int, user_question: str, bot, chat_id: int) -> str:
    """
    Обрабатывает вопрос по уроку, возвращает ответ и отправляет кнопки.
    Возвращает ответ (для возможного использования в voice).
    """
    from data.users import get_user_state, set_user_state
    from services.deepseek import chat
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    user_state = get_user_state(user_id)
    qa_data = user_state.get("lesson_qa", {})
    if not qa_data.get("active"):
        return None

    topic_key = qa_data.get("topic_key")
    topic_title = qa_data.get("topic_title", "этой теме")

    # Проверка на "бред"
    if len(user_question) < 3 or user_question.count(user_question[0]) > len(user_question) * 0.7:
        answer = "❓ Пожалуйста, сформулируйте вопрос понятнее. Я помогу разобраться с темой."
    else:
        # Получаем историю вопросов
        question_history = qa_data.get("history", [])
        history_text = ""
        if question_history:
            history_text = "Предыдущие вопросы и ответы:\n" + "\n".join(question_history[-3:]) + "\n\n"

        # Номер страницы
        page_num = user_state.get("current_lesson", {}).get("page", 0) + 1
        page_hint = f" (сейчас пользователь на странице {page_num})" if page_num else ""

        prompt = f"""
Ты преподаватель английского. Ученик изучает тему "{topic_title}".
Вопрос: {user_question}

{history_text}

ПРАВИЛА:
1. Если вопрос НЕ относится к теме "{topic_title}" (например, про другое время, другую грамматику, или вообще не про английский), вежливо ответь:
   "Извините, я помогаю только с темой '{topic_title}'. Какой у вас вопрос по этой теме?"
   (не объясняй ничего лишнего, просто попроси задать вопрос по теме)

2. Если вопрос относится к теме, дай КРАТКИЙ ответ (3-4 предложения) на русском языке. Можешь добавить пример из жизни.

3. Не добавляй лишних пояснений и приветствий. Ответ должен быть максимально коротким.

4. Если вопрос лишь частично относится к теме, сначала уточни:
   "Ваш вопрос касается темы '{topic_title}'? Если да, пожалуйста, задайте его конкретнее."

5. Ты НИКОГДА не проверяешь ответы ученика. Ты НЕ даёшь заданий. Ты НЕ просишь продолжить фразу. Ты НЕ оцениваешь правильность написанного. Твоя задача — ТОЛЬКО объяснять теорию и отвечать на вопросы по теме.

6. Если ученик написал что-то похожее на ответ на упражнение (например, предложение с пропуском, перевод слова), ты должен ответить:
   "Извините, я здесь только для объяснений. Если у вас есть вопрос по теме '{topic_title}', пожалуйста, задайте его."

7. НЕ используй слова «проверю», «составьте», «продолжите», «напишите». Ты не проверяешь, ты объясняешь.

Ответ должен быть дружелюбным.
"""
        answer = chat(prompt, max_tokens=400, temperature=0.5)

        # Сохраняем историю
        question_history.append(f"Вопрос: {user_question}\nОтвет: {answer}")
        if len(question_history) > 3:
            question_history.pop(0)
        user_state["lesson_qa"]["history"] = question_history
        set_user_state(user_id, user_state)

    # Кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Всё понятно", callback_data=f"lesson_understand_{topic_key}")],
        [InlineKeyboardButton(text="🔄 Объяснить по-другому", callback_data=f"lesson_reask_{topic_key}")],
        [InlineKeyboardButton(text="🔙 Назад к уроку", callback_data=f"back_to_lesson_{topic_key}")]
    ])
    await bot.send_message(chat_id=chat_id, text=answer, reply_markup=keyboard)
    return answer

LESSON_CONTENT = {}
LESSON_CONTENT.update(LEVEL_A1_CONTENT)
LESSON_CONTENT.update(LEVEL_A2_CONTENT)
LESSON_CONTENT.update(LEVEL_B1_CONTENT)
LESSON_CONTENT.update(LEVEL_B2_CONTENT)
LESSON_CONTENT.update(LEVEL_C1_CONTENT)
LESSON_CONTENT.update(LEVEL_C2_CONTENT)
LESSON_CONTENT.update(THEMATIC_NEW_CONTENT)
THEMATIC_TOPICS = [
    "Inversion after negative adverbs",
    "Inversion for emphasis",
    "Cleft sentences",
    "Ellipsis and substitution",
    "Mixed conditionals",
    "Conditionals without if",
    "Modal Perfect advanced",
    "Passive with modal verbs",
    "Future Perfect Continuous",
    "Future in the Past advanced",
    "Gerund vs infinitive advanced",
    "Perfect gerund and infinitive",
    "Passive gerund and infinitive",
    "Reported speech advanced",
    "Reporting verbs",
    "Reported questions advanced",
    "Passive with reporting verbs",
    "Passive with prepositions",
    "Impersonal passive",
    "Reduced relative clauses",
    "Clauses of concession advanced",
    "Clauses of purpose advanced",
    "Clauses of result advanced",
    "Expressing necessity",
    "Expressing criticism and regret",
    "Ability expressions",
    "Comparative structures as as",
    "The more the more",
    "Too enough",
    "Speaking cliches",
    "Discourse markers",
    "Fillers hesitation",
    "Word formation advanced",
    "Latin and Greek roots",
    "False friends advanced",
    "Confusing words",
    "Phrasal verbs C1 C2 part 1",
    "Phrasal verbs C1 C2 part 2",
    "Idioms C1",
    "Idioms C2",
    "Punctuation",
    "Formal informal register",
    "Hedging",
    "Rhetorical devices"

]

THEMATIC_TOPICS_RU = [
    "Инверсия после отрицательных наречий",
    "Инверсия для эмфазы",
    "Расщеплённые предложения",
    "Эллипсис и замена",
    "Смешанные условные предложения",
    "Условные предложения без if",
    "Modal Perfect (углубление)",
    "Пассив с модальными глаголами",
    "Future Perfect Continuous",
    "Future in the Past (сложные случаи)",
    "Герундий и инфинитив – сложные глаголы",
    "Перфектный герундий и инфинитив",
    "Пассивный герундий и инфинитив",
    "Косвенная речь – сложные случаи",
    "Глаголы передачи речи",
    "Косвенные вопросы (продвинутые)",
    "Пассив с глаголами передачи информации",
    "Пассив с предлогами",
    "Безличный пассив",
    "Сокращённые определительные придаточные",
    "Придаточные уступки (сложные нюансы)",
    "Придаточные цели",
    "Придаточные следствия",
    "Выражение необходимости",
    "Выражение критики и сожаления",
    "Способность (can, could, be able to, manage to, succeed in)",
    "Конструкции сравнения as...as, not so...as, than, less...than",
    "Конструкция the more... the more",
    "Конструкции too / enough",
    "Разговорные клише",
    "Дискурсивные маркеры",
    "Заполнители пауз",
    "Словообразование (продвинутое)",
    "Латинские и греческие корни",
    "Ложные друзья переводчика",
    "Часто путаемые слова",
    "Фразовые глаголы C1-C2 (часть 1)",
    "Фразовые глаголы C1-C2 (часть 2)",
    "Идиомы C1",
    "Идиомы C2",
    "Пунктуация в английском",
    "Формальный и неформальный английский",
    "Hedging (смягчение утверждений)",
    "Риторические приёмы"
]

MODULES_A1 = {
    "1": {"name": "📘 Модуль 1: Основы и знакомство", "lessons": ["alphabet", "numbers120", "tobepositive", "tobenegaquestion", "countries", "pronouns", "plural", "questionwords", "thereisare", "prepositionsplace", "adjectives", "presentsimple"]},
    "2": {"name": "📙 Модуль 2: Действия и события", "lessons": ["prescont", "presimplevscont", "tobePast", "pastSimpleRegular", "pastSimpleIrregular", "futureGoingTo", "modalCan", "modalMust", "ordinalNumbers", "adverbsFrequency", "prepositionsTime"]},
    "3": {"name": "📗 Модуль 3: Мир вокруг нас", "lessons": ["foodVocabulary", "countableUncountable", "clothesVocabulary", "weatherVocabulary", "dailyRoutine", "familyVocabulary", "houseVocabulary", "townVocabulary", "directions", "jobVocabulary", "hobbyVocabulary", "holidayVocabulary", "shoppingVocabulary", "bodyVocabulary"]}
}

MODULES_A2 = {
    "1": {
        "name": "📘 Модуль 1: Грамматика (повторение и углубление)",
        "lessons": ["presimplevscont_advanced", "pastsimple_review", "pastcontinuous", "pastsimple_vs_pastcontinuous", "presentperfect_simple", "presentperfect_vs_pastsimple", "usedto", "future_forms", "future_comparison"]
    },
    "2": {
        "name": "📙 Модуль 2: Модальные глаголы и условные предложения",
        "lessons": ["modal_can_could_may_might", "modal_should_ought", "modal_must_have_to", "mustnt_vs_dont_have_to", "conditionals_0", "conditionals_1"]
    },
    "3": {
        "name": "📗 Модуль 3: Пассивный залог и косвенная речь",
        "lessons": ["passive_present", "passive_past", "reported_speech_statements", "reported_speech_questions", "indirect_questions"]
    },
    "4": {
        "name": "📘 Модуль 4: Прилагательные и наречия (углубление)",
        "lessons": ["comparatives_superlatives", "adverbs_manner", "adjectives_order", "comparative_structures"]
    },
    "5": {
        "name": "📙 Модуль 5: Грамматические конструкции",
        "lessons": ["too_enough", "gerund_infinitive", "prepositions_time_place_advanced", "relative_clauses"]
    },
    "6": {
        "name": "📗 Модуль 6: Лексика по темам A2",
        "lessons": ["work_career", "travel_transport", "food_restaurant", "health_fitness", "technology_internet", "environment_weather", "feelings_emotions", "relationships_communication", "news_current_events", "idioms_phrases"]
    }
}

MODULES_B1 = {
    "1": {"name": "📘 Модуль 1: Времена и аспекты (углубление)", "lessons": ["present_tenses_review", "past_tenses_review", "present_perfect_continuous", "past_perfect", "past_perfect_continuous", "future_continuous", "future_perfect", "future_in_the_past", "time_clauses"]},
    "2": {"name": "📙 Модуль 2: Модальные глаголы (углубление)", "lessons": ["modal_ability", "modal_permission_obligation", "modal_probability", "modal_advice_criticism", "modal_perfect"]},
    "3": {"name": "📗 Модуль 3: Условные предложения и желания", "lessons": ["conditionals_2", "conditionals_3", "mixed_conditionals", "wish_if_only", "would_rather_prefer"]},
    "4": {"name": "📘 Модуль 4: Герундий и инфинитив (углубление)", "lessons": ["gerund_vs_infinitive_advanced", "verbs_with_both", "passive_gerund_infinitive"]},
    "5": {"name": "📙 Модуль 5: Пассивный залог (углубление)", "lessons": ["passive_all_tenses", "passive_with_modals", "impersonal_passive", "causative_have_get"]},
    "6": {"name": "📗 Модуль 6: Косвенная речь (углубление)", "lessons": ["reported_speech_advanced", "reported_commands_requests", "reported_questions_advanced", "reporting_verbs"]},
    "7": {"name": "📘 Модуль 7: Придаточные и связки", "lessons": ["relative_clauses_advanced", "clauses_of_concession", "clauses_of_purpose", "clauses_of_result"]},
    "8": {"name": "📙 Модуль 8: Лексика B1", "lessons": ["education_learning", "money_finance", "media_advertising", "crime_law", "personality_character", "workplace", "global_issues", "phrasal_verbs_1", "phrasal_verbs_2", "word_formation"]}
}

MODULES_B2 = {
    "1": {"name": "📘 Модуль 1: Сложные времена и аспекты", "lessons": ["narrative_tenses", "future_continuous_perfect", "future_perfect_continuous", "present_perfect_simple_continuous_review", "past_perfect_continuous_advanced", "time_clauses_advanced"]},
    "2": {"name": "📙 Модуль 2: Модальные глаголы (продвинутый)", "lessons": ["modal_perfect_advanced", "modal_passive", "modal_expressions_ability", "modal_expressions_necessity", "modal_expressions_criticism"]},
    "3": {"name": "📗 Модуль 3: Условные предложения (продвинутые)", "lessons": ["conditionals_mixed", "conditionals_alternatives", "conditionals_inversion", "wish_if_only_advanced", "would_rather_would_sooner"]},
    "4": {"name": "📘 Модуль 4: Инфинитив и герундий (продвинутые)", "lessons": ["infinitive_gerund_advanced", "perfect_infinitive_gerund", "passive_infinitive_gerund", "verbs_of_perception", "causative_advanced"]},
    "5": {"name": "📙 Модуль 5: Пассивный залог (продвинутый)", "lessons": ["passive_reporting_verbs", "passive_with_prepositions", "impersonal_passive_advanced", "causative_passive"]},
    "6": {"name": "📗 Модуль 6: Косвенная речь (продвинутая)", "lessons": ["reported_speech_advanced_2", "reported_speech_mix", "reporting_verbs_advanced", "reporting_verbs_patterns"]},
    "7": {"name": "📘 Модуль 7: Придаточные и связки (продвинутые)", "lessons": ["relative_clauses_reduced", "cleft_sentences", "inversion_negative", "inversion_emphatic", "conjunctions_advanced"]},
    "8": {"name": "📙 Модуль 8: Лексика B2", "lessons": ["work_career_b2", "education_b2", "health_medicine", "environment_b2", "science_technology", "media_communication", "crime_punishment", "politics_government", "economy_business", "phrasal_verbs_b2", "phrasal_verbs_b2_2", "idioms_b2"]}
}

MODULES_C1 = {
    "1": {"name": "📘 Модуль 1: Сложные времена и аспекты (C1)", "lessons": ["future_perfect_continuous_advanced", "future_in_the_past_advanced", "past_perfect_continuous_advanced2", "present_perfect_continuous_advanced", "narrative_tenses_advanced", "time_clauses_advanced_c1"]},
    "2": {"name": "📙 Модуль 2: Модальные глаголы (C1)", "lessons": ["modal_verbs_advanced_c1", "modal_perfect_advanced_c1", "modal_passive_advanced_c1", "modal_expressions_necessity_adv", "modal_expressions_criticism_adv"]},
    "3": {"name": "📗 Модуль 3: Условные предложения (C1)", "lessons": ["conditionals_mixed_advanced", "conditionals_alternatives_advanced", "conditionals_inversion_advanced", "wish_if_only_advanced_c1", "would_rather_prefer_advanced"]},
    "4": {"name": "📘 Модуль 4: Инфинитив и герундий (C1)", "lessons": ["infinitive_gerund_advanced_c1", "perfect_infinitive_gerund_adv", "passive_infinitive_gerund_adv", "verbs_of_perception_advanced", "causative_advanced_c1"]},
    "5": {"name": "📙 Модуль 5: Пассивный залог (C1)", "lessons": ["passive_reporting_verbs_advanced", "passive_with_prepositions_adv", "impersonal_passive_advanced_c1", "causative_passive_advanced"]},
    "6": {"name": "📗 Модуль 6: Косвенная речь (C1)", "lessons": ["reported_speech_advanced_c1", "reported_speech_mix_advanced", "reporting_verbs_advanced_c1", "reporting_verbs_patterns_c1"]},
    "7": {"name": "📘 Модуль 7: Придаточные и связки (C1)", "lessons": ["relative_clauses_reduced_c1", "cleft_sentences_advanced", "inversion_negative_advanced", "inversion_emphatic_advanced", "conjunctions_advanced_c1"]},
    "8": {"name": "📙 Модуль 8: Лексика C1", "lessons": ["academic_writing", "idioms_c1", "phrasal_verbs_c1", "phrasal_verbs_c1_2", "collocations_c1", "word_formation_c1", "formal_informal_language", "business_english_c1"]}
}

MODULES_C2 = {
    "1": {"name": "📘 Модуль 1: Регистры и стилистика", "lessons": ["formal_vs_informal_advanced", "analyzing_text_style", "register_switching", "irony_sarcasm_understatement"]},
    "2": {"name": "📙 Модуль 2: Углублённые идиомы и фразовые глаголы", "lessons": ["idioms_c2_1", "idioms_c2_2", "phrasal_verbs_c2_1", "phrasal_verbs_c2_2"]},
    "3": {"name": "📗 Модуль 3: Коллокации и словообразование", "lessons": ["collocations_c2", "word_formation_c2", "root_words", "false_friends"]},
    "4": {"name": "📘 Модуль 4: Эмфатические и риторические конструкции", "lessons": ["cleft_sentences_emphatic", "inversion_emphatic_c2", "negative_inversion_c2", "ellipsis_substitution"]},
    "5": {"name": "📙 Модуль 5: Выражение неуверенности, предположения, уступки", "lessons": ["hedging_c2", "concession_clauses", "modal_expressions_guessing", "future_past_modals"]},
    "6": {"name": "📗 Модуль 6: Речевые клише и дискурсивные маркеры", "lessons": ["discourse_markers", "fillers_hesitation", "speaking_cliches", "transitions_advanced"]},
    "7": {"name": "📘 Модуль 7: Анализ ошибок и выбор между похожими словами", "lessons": ["confusing_words", "common_mistakes_c2", "synonyms_nuances", "advanced_prepositions"]},
    "8": {"name": "📙 Модуль 8: Дебаты и аргументация", "lessons": ["debate_structures", "persuasive_language", "counterargument_cliches", "topic_based_debates"]}
}

ALL_MODULES = {"A1": MODULES_A1, "A2": MODULES_A2, "B1": MODULES_B1, "B2": MODULES_B2, "C1": MODULES_C1, "C2": MODULES_C2}

LESSON_NAMES = {
# Названия для A1 (вставьте в LESSON_NAMES)
"alphabet": "🔤 Алфавит и произношение",
"numbers120": "🔢 Числа 1‑20",
"tobepositive": "✅ Глагол to be (утверждение)",
"tobenegaquestion": "❓ Глагол to be (отрицание и вопрос)",
"countries": "🌍 Страны и национальности",
"pronouns": "📌 Личные и притяжательные местоимения",
"plural": "📚 Множественное число существительных",
"questionwords": "❓ Вопросительные слова",
"thereisare": "🏠 Конструкция there is / there are",
"prepositionsplace": "📍 Предлоги места",
"adjectives": "🎨 Прилагательные (цвета, размеры, описания)",
"presentsimple": "⏰ Present Simple",
"prescont": "⚡ Present Continuous",
"presimplevscont": "🔄 Present Simple vs Continuous",
"tobePast": "📆 Глагол to be в прошедшем (was/were)",
"pastSimpleRegular": "✔️ Past Simple (правильные глаголы)",
"pastSimpleIrregular": "⚠️ Past Simple (неправильные глаголы)",
"futureGoingTo": "🔮 Конструкция going to (планы)",
"modalCan": "💪 Модальный глагол can",
"modalMust": "🔔 Модальный глагол must",
"ordinalNumbers": "🥇 Порядковые числительные",
"adverbsFrequency": "📊 Наречия частотности",
"prepositionsTime": "⏰ Предлоги времени (at, in, on)",
"foodVocabulary": "🍎 Еда и напитки",
"countableUncountable": "🔢 Исчисляемые / неисчисляемые существительные",
"clothesVocabulary": "👕 Одежда",
"weatherVocabulary": "☀️ Погода",
"dailyRoutine": "⏳ Режим дня",
"familyVocabulary": "👪 Семья",
"houseVocabulary": "🏠 Дом и комната",
"townVocabulary": "🏙️ Город (места)",
"directions": "🗺️ Как спросить и объяснить дорогу",
"jobVocabulary": "💼 Профессии",
"hobbyVocabulary": "🎨 Хобби и свободное время",
"holidayVocabulary": "✈️ Отпуск и путешествия",
"shoppingVocabulary": "🛒 Покупки",
"bodyVocabulary": "🦵 Тело человека",
    # A1 (все названия – они уже у вас есть, здесь привожу только для A2)
    # Для экономии места я не повторяю A1, но они должны быть. Если у вас их нет – добавьте из старого файла.
    # Ниже – все названия A2 (для заглушек). Вы их потом не меняете, только содержимое уроков.
    "presimplevscont_advanced": "📘 Present Simple vs Continuous (углублённо)",
    "pastsimple_review": "📖 Past Simple (повторение)",
    "pastcontinuous": "⏳ Past Continuous",
    "pastsimple_vs_pastcontinuous": "⚖️ Past Simple vs Past Continuous",
    "presentperfect_simple": "✅ Present Perfect Simple",
    "presentperfect_vs_pastsimple": "⚖️ Present Perfect vs Past Simple",
    "usedto": "🕰️ Конструкция used to",
    "future_forms": "🔮 Будущее время (will, going to, Present Continuous)",
    "future_comparison": "📊 Сравнение способов выражения будущего",
    "modal_can_could_may_might": "🔧 Модальные глаголы: can, could, may, might",
    "modal_should_ought": "💡 Модальные глаголы: should, ought to",
    "modal_must_have_to": "🔔 Модальные глаголы: must, have to",
    "mustnt_vs_dont_have_to": "🚫 Mustn't vs don't have to",
    "conditionals_0": "🔁 Условные предложения 0 типа",
    "conditionals_1": "🔁 Условные предложения 1 типа",
    "passive_present": "📦 Пассивный залог (настоящее время)",
    "passive_past": "📦 Пассивный залог (прошедшее время)",
    "reported_speech_statements": "🗣️ Косвенная речь (утверждения)",
    "reported_speech_questions": "❓ Косвенная речь (вопросы)",
    "indirect_questions": "🤔 Косвенные вопросы",
    "comparatives_superlatives": "📈 Степени сравнения прилагательных",
    "adverbs_manner": "🎯 Наречия образа действия",
    "adjectives_order": "📚 Порядок прилагательных",
    "comparative_structures": "📊 Сравнительные конструкции",
    "too_enough": "⚖️ too / enough",
    "gerund_infinitive": "📝 Герундий и инфинитив",
    "prepositions_time_place_advanced": "📍 Предлоги времени и места (углубление)",
    "relative_clauses": "🔗 Определительные придаточные",
    "work_career": "💼 Работа и карьера",
    "travel_transport": "✈️ Путешествия и транспорт",
    "food_restaurant": "🍽️ Еда и ресторан",
    "health_fitness": "🏋️ Здоровье и фитнес",
    "technology_internet": "📱 Технологии и интернет",
    "environment_weather": "🌍 Окружающая среда и погода",
    "feelings_emotions": "😊 Чувства и эмоции",
    "relationships_communication": "👥 Отношения и общение",
    "news_current_events": "📰 Новости и текущие события",
    "idioms_phrases": "💬 Разговорные фразы и идиомы",
    # B1 модуль 1
    "present_tenses_review": "📖 Present Tenses (повторение)",
    "past_tenses_review": "📖 Past Tenses (повторение)",
    "present_perfect_continuous": "🔄 Present Perfect Continuous (углубление)",
    "past_perfect": "⏳ Past Perfect",
    "past_perfect_continuous": "⏳ Past Perfect Continuous",
    "future_continuous": "🔮 Future Continuous",
    "future_perfect": "🔮 Future Perfect",
    "future_in_the_past": "📅 Future in the Past",
    "time_clauses": "⏰ Придаточные времени",
    # B1 модуль 2
    "modal_ability": "💪 Модальные глаголы: способность",
    "modal_permission_obligation": "⚖️ Модальные глаголы: разрешение, обязанность",
    "modal_probability": "🎲 Модальные глаголы: вероятность",
    "modal_advice_criticism": "💡 Модальные глаголы: совет, критика",
    "modal_perfect": "✅ Modal Perfect",
    # B1 модуль 3
    "conditionals_2": "🔁 Условные предложения 2 типа",
    "conditionals_3": "🔁 Условные предложения 3 типа",
    "mixed_conditionals": "🔄 Смешанные условные",
    "wish_if_only": "😔 Конструкции I wish, If only",
    "would_rather_prefer": "⚖️ Конструкции would rather, prefer",
    # B1 модуль 4
    "gerund_vs_infinitive_advanced": "📝 Герундий vs инфинитив (сложные случаи)",
    "verbs_with_both": "🔄 Глаголы с герундием и инфинитивом (смена смысла)",
    "passive_gerund_infinitive": "📦 Пассивный герундий и инфинитив",
    # B1 модуль 5
    "passive_all_tenses": "📦 Пассивный залог (все времена)",
    "passive_with_modals": "📦 Пассив с модальными глаголами",
    "impersonal_passive": "📦 Безличный пассив (It is said that…)",
    "causative_have_get": "🔧 Конструкция have/get something done",
    # B1 модуль 6
    "reported_speech_advanced": "🗣️ Косвенная речь (сложные случаи)",
    "reported_commands_requests": "🗣️ Косвенная речь: приказы и просьбы",
    "reported_questions_advanced": "❓ Косвенные вопросы (сложные случаи)",
    "reporting_verbs": "📢 Глаголы для передачи речи",
    # B1 модуль 7
    "relative_clauses_advanced": "🔗 Определительные придаточные (defining/non-defining)",
    "clauses_of_concession": "🧩 Придаточные уступки (although, despite)",
    "clauses_of_purpose": "🎯 Придаточные цели (to, in order to, so that)",
    "clauses_of_result": "💥 Придаточные следствия (so…that, such…that)",
    # B1 модуль 8
    "education_learning": "📚 Образование и обучение",
    "money_finance": "💰 Деньги и финансы",
    "media_advertising": "📺 Медиа и реклама",
    "crime_law": "⚖️ Преступления и закон",
    "personality_character": "🧠 Характер человека (углубление)",
    "workplace": "💼 Рабочая среда",
    "global_issues": "🌍 Глобальные проблемы",
    "phrasal_verbs_1": "🔤 Фразовые глаголы (часть 1)",
    "phrasal_verbs_2": "🔤 Фразовые глаголы (часть 2)",
    "word_formation": "🔨 Словообразование",
    # B2 модуль 1
    "narrative_tenses": "📖 Narrative Tenses (Past Tenses in Stories)",
    "future_continuous_perfect": "🔮 Future Continuous vs Future Perfect (повторение)",
    "future_perfect_continuous": "⏳ Future Perfect Continuous",
    "present_perfect_simple_continuous_review": "🔄 Present Perfect Simple vs Continuous (сравнение)",
    "past_perfect_continuous_advanced": "⏪ Past Perfect Continuous (сложные случаи)",
    "time_clauses_advanced": "⏰ Придаточные времени (as long as, once, by the time)",
    # B2 модуль 2
    "modal_perfect_advanced": "✅ Modal Perfect (must have done, could have done)",
    "modal_passive": "📦 Пассив с модальными глаголами",
    "modal_expressions_ability": "💪 Выражение способности (manage to, succeed in)",
    "modal_expressions_necessity": "⚖️ Выражение необходимости (needn't have done)",
    "modal_expressions_criticism": "😔 Выражение критики и сожаления",
    # B2 модуль 3
    "conditionals_mixed": "🔄 Смешанные условные",
    "conditionals_alternatives": "🔁 Альтернативы if (unless, provided that)",
    "conditionals_inversion": "🔄 Инверсия в условных (Had I known...)",
    "wish_if_only_advanced": "😟 I wish / If only (продвинутые)",
    "would_rather_would_sooner": "⚖️ would rather / would sooner",
    # B2 модуль 4
    "infinitive_gerund_advanced": "📝 Инфинитив и герундий (сложные глаголы)",
    "perfect_infinitive_gerund": "⏪ Перфектный инфинитив и герундий",
    "passive_infinitive_gerund": "📦 Пассивный инфинитив и герундий",
    "verbs_of_perception": "👀 Глаголы восприятия (see, hear, watch)",
    "causative_advanced": "🔧 Каузатив (have/get something done, have someone do)",
    # B2 модуль 5
    "passive_reporting_verbs": "🗣️ Пассив с глаголами передачи информации",
    "passive_with_prepositions": "📍 Пассив с предлогами (was laughed at)",
    "impersonal_passive_advanced": "📰 Безличный пассив (It is said that...)",
    "causative_passive": "🔨 Каузативный пассив (have/get something done)",
    # B2 модуль 6
    "reported_speech_advanced_2": "🗣️ Косвенная речь (сложные случаи)",
    "reported_speech_mix": "🔄 Смешение времён в косвенной речи",
    "reporting_verbs_advanced": "📢 Глаголы передачи речи (advise, accuse, boast)",
    "reporting_verbs_patterns": "📋 Паттерны глаголов передачи речи",
    # B2 модуль 7
    "relative_clauses_reduced": "✂️ Сокращённые определительные придаточные",
    "cleft_sentences": "🔍 Расщеплённые предложения (It was... that...)",
    "inversion_negative": "🔄 Инверсия после отрицательных наречий",
    "inversion_emphatic": "❗ Инверсия для эмфазы (Only then, Little did he know)",
    "conjunctions_advanced": "🔗 Союзы и связки (however, nevertheless, whereas)",
    # B2 модуль 8
    "work_career_b2": "💼 Работа и карьера (B2)",
    "education_b2": "🎓 Образование (B2)",
    "health_medicine": "🏥 Здоровье и медицина",
    "environment_b2": "🌍 Окружающая среда (B2)",
    "science_technology": "🔬 Наука и технологии",
    "media_communication": "📺 Медиа и коммуникация",
    "crime_punishment": "⚖️ Преступления и наказания",
    "politics_government": "🏛️ Политика и правительство",
    "economy_business": "📊 Экономика и бизнес",
    "phrasal_verbs_b2": "🔤 Фразовые глаголы B2 (часть 1)",
    "phrasal_verbs_b2_2": "🔤 Фразовые глаголы B2 (часть 2)",
    "idioms_b2": "💬 Идиомы и устойчивые выражения B2",
    # C1 модуль 1
    "future_perfect_continuous_advanced": "⏳ Future Perfect Continuous (углубление)",
    "future_in_the_past_advanced": "📅 Future in the Past (сложные случаи)",
    "past_perfect_continuous_advanced2": "⏪ Past Perfect Continuous (for/since)",
    "present_perfect_continuous_advanced": "🔄 Present Perfect Continuous (результат/длительность)",
    "narrative_tenses_advanced": "📖 Narrative Tenses (углублённо)",
    "time_clauses_advanced_c1": "⏰ Придаточные времени (so long as, once)",
    # C1 модуль 2
    "modal_verbs_advanced_c1": "🎯 Модальные глаголы (вероятность)",
    "modal_perfect_advanced_c1": "✅ Modal Perfect (сложные случаи)",
    "modal_passive_advanced_c1": "📦 Пассив с модальными (углубление)",
    "modal_expressions_necessity_adv": "⚖️ Выражение необходимости (need, needn't)",
    "modal_expressions_criticism_adv": "😔 Критика и сожаление (should have done)",
    # C1 модуль 3
    "conditionals_mixed_advanced": "🔄 Смешанные условные (сложные)",
    "conditionals_alternatives_advanced": "🔁 Альтернативы if (provided, as long as)",
    "conditionals_inversion_advanced": "🔄 Инверсия в условных (Had I known)",
    "wish_if_only_advanced_c1": "😟 I wish / If only (C1)",
    "would_rather_prefer_advanced": "⚖️ would rather / prefer (оттенки)",
    # C1 модуль 4
    "infinitive_gerund_advanced_c1": "📝 Инфинитив и герундий (сложные)",
    "perfect_infinitive_gerund_adv": "⏪ Перфектный инфинитив/герундий",
    "passive_infinitive_gerund_adv": "📦 Пассивный инфинитив/герундий",
    "verbs_of_perception_advanced": "👀 Глаголы восприятия (нюансы)",
    "causative_advanced_c1": "🔧 Каузатив (углубление)",
    # C1 модуль 5
    "passive_reporting_verbs_advanced": "🗣️ Пассив с глаголами передачи информации",
    "passive_with_prepositions_adv": "📍 Пассив с предлогами (редкие случаи)",
    "impersonal_passive_advanced_c1": "📰 Безличный пассив (все времена)",
    "causative_passive_advanced": "🔨 Каузативный пассив (углубление)",
    # C1 модуль 6
    "reported_speech_advanced_c1": "🗣️ Косвенная речь (сложные случаи)",
    "reported_speech_mix_advanced": "🔄 Косвенная речь (актуальность)",
    "reporting_verbs_advanced_c1": "📢 Глаголы передачи речи (все паттерны)",
    "reporting_verbs_patterns_c1": "📋 Паттерны глаголов передачи речи",
    # C1 модуль 7
    "relative_clauses_reduced_c1": "✂️ Сокращённые определительные придаточные",
    "cleft_sentences_advanced": "🔍 Расщеплённые предложения (все типы)",
    "inversion_negative_advanced": "🔄 Инверсия после отрицательных наречий",
    "inversion_emphatic_advanced": "❗ Инверсия для эмфазы",
    "conjunctions_advanced_c1": "🔗 Союзы и связки (C1)",
    # C1 модуль 8
    "academic_writing": "📝 Академическая письменная речь",
    "idioms_c1": "💬 Идиомы C1",
    "phrasal_verbs_c1": "🔤 Фразовые глаголы C1 (ч.1)",
    "phrasal_verbs_c1_2": "🔤 Фразовые глаголы C1 (ч.2)",
    "collocations_c1": "🔗 Коллокации C1",
    "word_formation_c1": "🔨 Словообразование C1",
    "formal_informal_language": "🎭 Формальный и неформальный английский",
    "business_english_c1": "💼 Деловой английский C1",
    # C2 модуль 1
    "formal_vs_informal_advanced": "🎭 Формальный vs неформальный (углублённо)",
    "analyzing_text_style": "📊 Анализ стиля текста",
    "register_switching": "🔄 Переключение регистров",
    "irony_sarcasm_understatement": "🎭 Ирония, сарказм, преуменьшение",
    # C2 модуль 2
    "idioms_c2_1": "💬 Идиомы C2 (ч.1)",
    "idioms_c2_2": "💬 Идиомы C2 (ч.2)",
    "phrasal_verbs_c2_1": "🔤 Фразовые глаголы C2 (ч.1)",
    "phrasal_verbs_c2_2": "🔤 Фразовые глаголы C2 (ч.2)",
    # C2 модуль 3
    "collocations_c2": "🔗 Коллокации C2",
    "word_formation_c2": "🔨 Словообразование C2",
    "root_words": "🌱 Латинские и греческие корни",
    "false_friends": "⚠️ Ложные друзья переводчика (C2)",
    # C2 модуль 4
    "cleft_sentences_emphatic": "🔍 Расщеплённые предложения (эмфаза)",
    "inversion_emphatic_c2": "🔄 Инверсия для эмфазы",
    "negative_inversion_c2": "🔄 Инверсия после отрицательных наречий",
    "ellipsis_substitution": "✂️ Эллипсис и замена",
    # C2 модуль 5
    "hedging_c2": "🤔 Выражение неуверенности (hedging)",
    "concession_clauses": "🧩 Придаточные уступки",
    "modal_expressions_guessing": "🎲 Модальные глаголы для предположений",
    "future_past_modals": "⏳ Модальные глаголы для будущего и прошлого",
    # C2 модуль 6
    "discourse_markers": "🔗 Дискурсивные маркеры",
    "fillers_hesitation": "🗣️ Заполнители пауз и хезитации",
    "speaking_cliches": "💬 Разговорные клише",
    "transitions_advanced": "📝 Продвинутые переходы",
    # C2 модуль 7
    "confusing_words": "❓ Часто путаемые слова",
    "common_mistakes_c2": "⚠️ Типичные ошибки C2",
    "synonyms_nuances": "🎨 Оттенки синонимов",
    "advanced_prepositions": "📍 Продвинутые предлоги",
    # C2 модуль 8
    "debate_structures": "⚖️ Структура дебатов",
    "persuasive_language": "🗣️ Язык убеждения",
    "counterargument_cliches": "🔄 Клише для контраргументации",
    "topic_based_debates": "🌍 Тематические дебаты",
}

user_page = {}

def get_thematic_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    start_idx = (page - 1) * 5
    end_idx = start_idx + 5
    page_topics_en = THEMATIC_TOPICS[start_idx:end_idx]
    page_topics_ru = THEMATIC_TOPICS_RU[start_idx:end_idx]
    buttons = []
    for idx, (topic_en, topic_ru) in enumerate(zip(page_topics_en, page_topics_ru), start=start_idx):
        buttons.append([InlineKeyboardButton(text=topic_ru, callback_data=f"thematic_{idx}")])
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀", callback_data="thematic_prev"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="thematic_none"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶", callback_data="thematic_next"))
    buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_modules_keyboard(level: str) -> InlineKeyboardMarkup:
    modules = ALL_MODULES.get(level, {})
    buttons = []
    for mod_id, mod_data in modules.items():
        if mod_data["lessons"]:
            buttons.append([InlineKeyboardButton(text=mod_data["name"], callback_data=f"module_{level}_{mod_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к уровням", callback_data="start_lessons")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_module_lessons_keyboard(level: str, module_id: str) -> InlineKeyboardMarkup:
    modules = ALL_MODULES.get(level, {})
    lessons = modules.get(module_id, {}).get("lessons", [])
    buttons = []
    for key in lessons:
        name = LESSON_NAMES.get(key, key)
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"lesson_{level}|{module_id}|{key}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад к модулям", callback_data=f"back_to_modules_{level}")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def show_lesson_page(message: Message, user_id: int, edit: bool = True):
    user_state = get_user_state(user_id)
    lesson = user_state.get("current_lesson")
    if not lesson:
        return
    key = lesson["key"]
    content = lesson["content"]
    page_idx = lesson.get("page", 0)
    pages = content["pages"]
    total_pages = len(pages)
    if page_idx >= total_pages:
        page_idx = total_pages - 1
    page = pages[page_idx]
    # Если это последняя страница, считаем урок пройденным
    if page_idx == total_pages - 1:
        from handlers.profile import update_stats_after_lesson
        update_stats_after_lesson(user_id)

    text = f"<b>📖 {lesson['topic']}</b>\n\n{page['text']}"

    nav_buttons = []
    if page_idx > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data="lesson_prev_page"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page_idx+1}/{total_pages}", callback_data="lesson_none"))
    if page_idx < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Далее ▶", callback_data="lesson_next_page"))

    # Определяем кнопку возврата: для тематических уроков – в меню тем, для уровневых – в модуль
    if lesson.get("source") == "thematic":
        back_callback = "thematic_menu"
        back_text = "🔙 Назад к темам"
    else:
        back_callback = f"back_to_module_{lesson.get('module_id', '1')}|{lesson.get('level', 'A1')}"
        back_text = "🔙 Назад к списку уроков"

    lesson_buttons = [
        [InlineKeyboardButton(text="🤔 Задать вопрос", callback_data=f"lesson_ask_{key}")],
        [InlineKeyboardButton(text="📝 Начать практику", callback_data=f"lesson_practice_{key}")],
        [InlineKeyboardButton(text=back_text, callback_data=back_callback)],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ]

    if page.get("has_audio_buttons") and key == "alphabet":
        letters = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']
        audio_rows = []
        for i in range(0, len(letters), 7):
            row = [InlineKeyboardButton(text=letter, callback_data=f"pronounce_{key}_{letter}") for letter in letters[i:i+7]]
            audio_rows.append(row)
        keyboard = InlineKeyboardMarkup(inline_keyboard=audio_rows + [nav_buttons] + lesson_buttons)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons] + lesson_buttons)

    if edit:
        if message.text == text and message.reply_markup == keyboard:
            return
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(lambda c: c.data == "start_lessons")
async def lessons_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if "lessons" not in user_state:
        user_state["lessons"] = {}
    set_user_state(user_id, user_state)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="A1 (Beginner)", callback_data="level_A1"), InlineKeyboardButton(text="A2 (Elementary)", callback_data="level_A2")],
        [InlineKeyboardButton(text="B1 (Intermediate)", callback_data="level_B1"), InlineKeyboardButton(text="B2 (Upper Intermediate)", callback_data="level_B2")],
        [InlineKeyboardButton(text="C1 (Advanced)", callback_data="level_C1")],
[InlineKeyboardButton(text="C2 (Proficiency)", callback_data="level_C2")],
        [InlineKeyboardButton(text="📚 Тематические уроки", callback_data="thematic_menu")],
        [InlineKeyboardButton(text="📊 Моё обучение", callback_data="my_learning")],
        [InlineKeyboardButton(text="📝 Пройти тест (уровень)", callback_data="placement_test")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "📚 Режим уроков\n\nВыберите уровень, чтобы начать системное обучение.\nИли откройте «Тематические уроки».",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("level_"))
async def level_chosen(callback: CallbackQuery):
    level = callback.data.split("_")[1]
    if level in ALL_MODULES:
        keyboard = get_modules_keyboard(level)
        await callback.message.edit_text(f"📖 Уровень {level}\n\nВыберите модуль:", reply_markup=keyboard, parse_mode="HTML")
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")]])
        await callback.message.edit_text(f"📖 Уровень {level}\n\n🚧 Режим в разработке.", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("module_"))
async def module_chosen(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) != 3:
        await callback.answer("Ошибка формата", show_alert=True)
        return
    level = parts[1]
    module_id = parts[2]
    keyboard = get_module_lessons_keyboard(level, module_id)
    module_name = ALL_MODULES.get(level, {}).get(module_id, {}).get("name", "Модуль")
    await callback.message.edit_text(f"📘 {module_name}\n\nВыберите урок:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_") and not any(c.data.startswith(x) for x in ("lesson_next_page", "lesson_prev_page", "lesson_none", "lesson_faq_", "lesson_ask_", "lesson_practice_", "lesson_understand_", "lesson_reask_")))
async def lesson_chosen(callback: CallbackQuery):
    raw = callback.data[7:]
    if "|" in raw:
        parts = raw.split("|")
        if len(parts) != 3:
            await callback.answer("Ошибка формата", show_alert=True)
            return
        level, module_id, lesson_key = parts
    else:
        await callback.answer("Ошибка формата", show_alert=True)
        return
    content = LESSON_CONTENT.get(lesson_key)
    if not content:
        await callback.answer("Урок не найден", show_alert=True)
        return
    topic_name = LESSON_NAMES.get(lesson_key, lesson_key)
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["current_lesson"] = {
        "topic": topic_name, "key": lesson_key, "content": content, "page": 0,
        "level": level, "module_id": module_id
    }
    set_user_state(user_id, user_state)
    await show_lesson_page(callback.message, user_id, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("back_to_module_"))
async def back_to_module(callback: CallbackQuery):
    raw = callback.data[15:]
    if "|" not in raw:
        await callback.answer("Ошибка формата", show_alert=True)
        return
    module_id, level = raw.split("|")
    keyboard = get_module_lessons_keyboard(level, module_id)
    module_name = ALL_MODULES.get(level, {}).get(module_id, {}).get("name", "Модуль")
    await callback.message.edit_text(f"📘 {module_name}\n\nВыберите урок:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("back_to_modules_"))
async def back_to_modules(callback: CallbackQuery):
    level = callback.data.split("_")[3]
    keyboard = get_modules_keyboard(level)
    await callback.message.edit_text(f"📖 Уровень {level}\n\nВыберите модуль:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ==================== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (навигация, FAQ, аудио) – они у вас уже есть ====================
# Здесь идут обработчики lesson_next_page, lesson_prev_page, lesson_faq, lesson_ask, lesson_practice, back_to_lesson,
# lesson_understand, lesson_reask, pronounce_letter, back_to_alphabet, thematic_lessons_menu и т.д.
# Чтобы не раздувать ответ, я опускаю их, но вы должны скопировать их из вашего текущего рабочего `handlers/lessons.py`
# ==================== НАВИГАЦИЯ ПО СТРАНИЦАМ УРОКА ====================
@router.callback_query(lambda c: c.data == "lesson_next_page")
async def lesson_next_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lesson = user_state.get("current_lesson")
    if not lesson:
        await callback.answer("Урок не найден", show_alert=True)
        return
    pages = lesson["content"]["pages"]
    current = lesson.get("page", 0)
    if current + 1 < len(pages):
        lesson["page"] = current + 1
        set_user_state(user_id, user_state)
        await show_lesson_page(callback.message, user_id, edit=True)
    else:
        await callback.answer("Это последняя страница", show_alert=True)
    await callback.answer()

@router.callback_query(lambda c: c.data == "lesson_prev_page")
async def lesson_prev_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lesson = user_state.get("current_lesson")
    if not lesson:
        await callback.answer("Урок не найден", show_alert=True)
        return
    current = lesson.get("page", 0)
    if current > 0:
        lesson["page"] = current - 1
        set_user_state(user_id, user_state)
        await show_lesson_page(callback.message, user_id, edit=True)
    else:
        await callback.answer("Это первая страница", show_alert=True)
    await callback.answer()

# ==================== FAQ, ВОПРОСЫ, ПРАКТИКА ====================
@router.callback_query(lambda c: c.data.startswith("lesson_faq_"))
async def lesson_faq(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    content = LESSON_CONTENT.get(key)
    if not content or not content.get("faq"):
        await callback.answer("FAQ не найдены", show_alert=True)
        return
    faq_text = "<b>❓ Часто задаваемые вопросы:</b>\n\n"
    for i, item in enumerate(content["faq"], 1):
        faq_text += f"<b>{i}. {item['question']}</b>\n{item['answer']}\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к уроку", callback_data=f"back_to_lesson_{key}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(faq_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_ask_"))
async def lesson_ask_start(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)          # <-- ОБЯЗАТЕЛЬНО добавить эту строку
    
    current_lesson = user_state.get("current_lesson", {})
    topic_title = current_lesson.get("topic", "этой теме")
    
    # Сбрасываем режим практики (если был)
    user_state["lesson_mode"] = None
    user_state["lesson_step"] = None
    user_state["lesson_task"] = None
    
    user_state["lesson_qa"] = {
        "active": True,
        "topic_key": key,
        "topic_title": topic_title
    }
    set_user_state(user_id, user_state)
    
    await callback.message.edit_text(
        "🤔 Задайте ваш вопрос по теме. Я постараюсь объяснить максимально просто, с примерами из жизни.\n\n"
        "Если вопрос не по теме, я мягко верну вас к материалу.\n\n"
        "Напишите свой вопрос текстом.",
        parse_mode="HTML"
    )
    await callback.answer()

# ========== ПРАКТИКА ==========
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


@router.callback_query(lambda c: c.data.startswith("lesson_practice_"))
async def lesson_practice_start(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    current_lesson = user_state.get("current_lesson", {})
    content = current_lesson.get("content")
    
    if not content or "practice_bank" not in content:
        await callback.answer("Для этого урока нет заданий. Сначала сгенерируйте их.", show_alert=True)
        return
    
    practice_bank = content["practice_bank"]
    if not practice_bank:
        await callback.answer("Банк заданий пуст.", show_alert=True)
        return
    
    # Берём первый вариант
    tasks = practice_bank[0]
    
    if "practice" not in user_state:
        user_state["practice"] = {}
    
    user_state["practice"][key] = {
        "tasks": tasks,
        "completed": [False]*len(tasks),
        "current_session": list(range(len(tasks))),
        "session_index": 0,
        "session_correct": 0,
        "skip_count": 0,
        "attempts": {}
    }
    user_state["practice_lesson_key"] = key
    set_user_state(user_id, user_state)
    await show_practice_task(callback.message, user_id, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("practice_hint_"))
async def practice_hint(callback: CallbackQuery):
    lesson_key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    practice = user_state.get("practice", {}).get(lesson_key)
    if not practice:
        await callback.answer("Нет практики")
        return
    idx = practice["session_index"]
    task = practice["tasks"][practice["current_session"][idx]]
    hint = task.get("hint", "Подсказки нет")
    await callback.answer(hint, show_alert=True)

@router.callback_query(lambda c: c.data.startswith("practice_skip_"))
async def practice_skip(callback: CallbackQuery):
    lesson_key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    practice = user_state.get("practice", {}).get(lesson_key)
    if practice and practice.get("skip_count", 0) < 3:
        practice["skip_count"] += 1
        practice["session_index"] += 1
        set_user_state(user_id, user_state)
        await show_practice_task(callback.message, user_id, edit=True)
        await callback.answer("Задание пропущено")
    else:
        await callback.answer("Лимит пропусков (3) исчерпан", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("practice_exit_"))
async def practice_exit(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["practice_lesson_key"] = None
    set_user_state(user_id, user_state)
    await callback.message.edit_text("Практика прервана. Возвращаюсь к уроку.")
    # Вернёмся к уроку
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("back_to_lesson_"))
async def back_to_lesson(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    
    # Берём current_lesson из состояния
    lesson = user_state.get("current_lesson")
    if lesson:
        # Показываем страницу урока
        await show_lesson_page(callback.message, user_id, edit=True)
        await callback.answer()
        return
    
    # Если почему-то current_lesson нет, отправляем в меню уроков
    await callback.message.edit_text("Урок не найден. Возвращаемся к списку уроков.")
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()
    return
    
    # Находим уровень и модуль (как было в старом коде)
    level = None
    module_id = "1"
    for lvl, modules in ALL_MODULES.items():
        for mid, mod in modules.items():
            if key in mod["lessons"]:
                level = lvl
                module_id = mid
                break
        if level:
            break
    if not level:
        level = "A1"
    
    user_state["current_lesson"] = {
        "topic": topic_name,
        "key": key,
        "content": content,
        "page": 0,
        "level": level,
        "module_id": module_id
    }
    set_user_state(user_id, user_state)
    await show_lesson_page(callback.message, user_id, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_understand_"))
async def lesson_understand(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    await callback.message.edit_text(
        "✨ Прекрасно! Тогда предлагаю попрактиковаться, чтобы закрепить материал.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Начать практику", callback_data=f"lesson_practice_{key}")],
            [InlineKeyboardButton(text="🔙 Назад к уроку", callback_data=f"back_to_lesson_{key}")]
        ]),
        parse_mode="HTML"
    )
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if "lesson_qa" in user_state:
        del user_state["lesson_qa"]
    set_user_state(user_id, user_state)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_reask_"))
async def lesson_reask(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["lesson_qa"] = {
        "active": True,
        "topic_key": key,
        "topic_title": LESSON_CONTENT.get(key, {}).get("title", "этой теме")
    }
    set_user_state(user_id, user_state)
    await callback.message.edit_text(
        "🤔 Попробуйте задать вопрос иначе, или уточните, что именно осталось непонятным.\n\nНапишите ваш вопрос:",
        parse_mode="HTML"
    )
    await callback.answer()

# ==================== АУДИО ДЛЯ БУКВ ====================
CACHE_DIR = "cached_audio/alphabet"
os.makedirs(CACHE_DIR, exist_ok=True)

LETTER_PRONUNCIATION = {
    'A': 'A — эй, как в слове Apple',
    'B': 'B — би, как в слове Boy',
    'C': 'C — си, как в слове Cat',
    'D': 'D — ди, как в слове Dog',
    'E': 'E — и, как в слове Egg',
    'F': 'F — эф, как в слове Fish',
    'G': 'G — джи, как в слове Girl',
    'H': 'H — эйч, как в слове Hat',
    'I': 'I — ай, как в слове Ice',
    'J': 'J — джей, как в слове Juice',
    'K': 'K — кей, как в слове Kite',
    'L': 'L — эл, как в слове Lion',
    'M': 'M — эм, как в слове Mother',
    'N': 'N — эн, как в слове Night',
    'O': 'O — оу, как в слове Orange',
    'P': 'P — пи, как в слове Pen',
    'Q': 'Q — кью, как в слове Queen',
    'R': 'R — ар, как в слове Red',
    'S': 'S — эс, как в слове Sun',
    'T': 'T — ти, как в слове Tea',
    'U': 'U — ю, как в слове Umbrella',
    'V': 'V — ви, как в слове Violin',
    'W': 'W — дабл-ю, как в слове Window',
    'X': 'X — экс, как в слове X-ray',
    'Y': 'Y — уай, как в слове Yellow',
    'Z': 'Z — зед, как в слове Zebra'
}

@router.callback_query(lambda c: c.data.startswith("pronounce_"))
async def pronounce_letter(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка формата", show_alert=True)
        return
    lesson_key = parts[1]
    letter = parts[2]

    cached_path = os.path.join(CACHE_DIR, f"{letter}.mp3")
    if os.path.exists(cached_path):
        voice = FSInputFile(cached_path)
        reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ещё раз", callback_data=f"pronounce_{lesson_key}_{letter}")],
            [InlineKeyboardButton(text="🔙 Назад к алфавиту", callback_data=f"back_to_alphabet_{lesson_key}")]
        ])
        await callback.message.answer_voice(voice, caption=f"🔊 {letter}", reply_markup=reply_keyboard)
        await callback.answer()
        return

    await callback.message.answer("🔊 Генерирую произношение... Подождите секунду.")
    text_to_speak = LETTER_PRONUNCIATION.get(letter, f"{letter}")
    audio_path = await text_to_voice(text_to_speak)

    if audio_path and os.path.exists(audio_path):
        import shutil
        shutil.copy(audio_path, cached_path)
        voice = FSInputFile(cached_path)
        reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ещё раз", callback_data=f"pronounce_{lesson_key}_{letter}")],
            [InlineKeyboardButton(text="🔙 Назад к алфавиту", callback_data=f"back_to_alphabet_{lesson_key}")]
        ])
        await callback.message.answer_voice(voice, caption=f"🔊 {letter}", reply_markup=reply_keyboard)
        os.unlink(audio_path)
    else:
        await callback.message.answer("❌ Не удалось сгенерировать произношение. Попробуйте позже.")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("back_to_alphabet_"))
async def back_to_alphabet(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка формата", show_alert=True)
        return
    lesson_key = parts[3]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    if user_state.get("current_lesson", {}).get("key") == lesson_key:
        lesson = user_state["current_lesson"]
        lesson["page"] = 0
        set_user_state(user_id, user_state)
        await show_lesson_page(callback.message, user_id, edit=True)
    else:
        await callback.message.answer("Урок не найден, вернитесь в меню тем.")
    await callback.answer()

# ==================== ТЕМАТИЧЕСКИЕ УРОКИ ====================
@router.callback_query(lambda c: c.data == "thematic_menu")
async def thematic_lessons_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + 4) // 5
    user_page[user_id] = 1
    keyboard = get_thematic_keyboard(1, total_pages)
    await callback.message.edit_text(
        "📚 Тематические уроки\n\nВыберите тему для изучения:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "thematic_next")
async def thematic_next_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + 4) // 5
    current = user_page.get(user_id, 1)
    if current < total_pages:
        user_page[user_id] = current + 1
        keyboard = get_thematic_keyboard(current + 1, total_pages)
        await callback.message.edit_text(
            "📚 Тематические уроки\n\nВыберите тему для изучения:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(lambda c: c.data == "thematic_prev")
async def thematic_prev_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    total_pages = (len(THEMATIC_TOPICS) + 4) // 5
    current = user_page.get(user_id, 1)
    if current > 1:
        user_page[user_id] = current - 1
        keyboard = get_thematic_keyboard(current - 1, total_pages)
        await callback.message.edit_text(
            "📚 Тематические уроки\n\nВыберите тему для изучения:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("thematic_") and c.data not in ("thematic_menu", "thematic_next", "thematic_prev", "thematic_none"))
async def show_thematic_lesson(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    topic_name = THEMATIC_TOPICS[idx]
    key = topic_name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("?", "")
    
    content = LESSON_CONTENT.get(key)
    if not content:
        # fallback
        main_part = topic_name.split("(")[0].strip().lower().replace(" ", "_")
        for k in LESSON_CONTENT.keys():
            if k.startswith(main_part):
                content = LESSON_CONTENT.get(k)
                break
    
    if not content:
        await callback.answer(f"Ключ не найден: {key}", show_alert=True)
        return

    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["current_lesson"] = {
        "topic": topic_name,
        "key": key,
        "content": content,
        "page": 0,
        "source": "thematic"   # важно для определения, что это тематический урок
    }
    set_user_state(user_id, user_state)
    # Вызываем show_lesson_page с edit=True (редактируем текущее сообщение меню)
    await show_lesson_page(callback.message, user_id, edit=True)
    await callback.answer()
# ==================== МОЁ ОБУЧЕНИЕ, ТЕСТ ====================
@router.callback_query(lambda c: c.data == "my_learning")
async def my_learning_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lessons_data = user_state.get("lessons", {})
    level = lessons_data.get("level", "не выбран")
    completed_topics = lessons_data.get("completed_topics", [])
    total_correct = lessons_data.get("total_correct", 0)
    total_wrong = lessons_data.get("total_wrong", 0)

    progress_text = f"📊 Ваш прогресс\n\n🎯 Уровень: {level}\n✅ Выполнено тем: {len(completed_topics)}\n📈 Правильных ответов: {total_correct}\n❌ Ошибок: {total_wrong}\n"
    if total_correct + total_wrong > 0:
        percent = round(total_correct / (total_correct + total_wrong) * 100)
        progress_text += f"📊 Точность: {percent}%\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Продолжить обучение", callback_data="continue_learning")],
        [InlineKeyboardButton(text="📅 План недели", callback_data="weekly_plan")],
        [InlineKeyboardButton(text="🔄 Сменить уровень", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")]
    ])
    await callback.message.edit_text(progress_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(lambda c: c.data == "continue_learning")
async def continue_learning(callback: CallbackQuery):
    await callback.message.edit_text("🚧 Режим продолжения обучения в разработке.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="my_learning")]
    ]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "weekly_plan")
async def weekly_plan_menu(callback: CallbackQuery):
    await callback.message.edit_text("📅 План недели в разработке.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="my_learning")]
    ]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "placement_test")
async def placement_test(callback: CallbackQuery):
    await callback.message.edit_text("📝 Тест на определение уровня в разработке.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_lessons")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ]))
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()
# ========== ПРАКТИКА ==========
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def parse_user_answers(text: str, expected_count: int) -> list:
    """
    Разбивает ответы по запятым. Каждый ответ может содержать пробелы.
    Если ответов меньше expected_count, дополняет пустыми строками.
    """
    # Разбиваем по запятым, удаляем лишние пробелы
    parts = [part.strip() for part in text.split(',') if part.strip()]
    # Дополняем до нужного количества
    while len(parts) < expected_count:
        parts.append("")
    # Обрезаем, если слишком много
    return parts[:expected_count]

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
    star = " ⭐" if task.get("star") else ""
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

@router.callback_query(lambda c: c.data.startswith("practice_hint_"))
async def practice_hint(callback: CallbackQuery):
    lesson_key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    practice = user_state.get("practice", {}).get(lesson_key)
    if not practice:
        await callback.answer("Нет практики")
        return
    task_idx = practice.get("session_index", 0)
    task = practice["tasks"][task_idx]
    # Показываем первую подсказку (первое пояснение)
    if task.get("subtasks"):
        hint = task["subtasks"][0].get("explanation", "Подсказка: проверьте правильность написания")
    else:
        hint = "Подсказки нет"
    await callback.answer(hint, show_alert=True)

@router.callback_query(lambda c: c.data.startswith("practice_skip_"))
async def practice_skip(callback: CallbackQuery):
    lesson_key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    practice = user_state.get("practice", {}).get(lesson_key)
    if practice and practice.get("skip_count", 0) < 3:
        practice["skip_count"] += 1
        practice["session_index"] += 1
        set_user_state(user_id, user_state)
        await show_practice_task(callback.message, user_id, edit=True)
        await callback.answer("Задание пропущено")
    else:
        await callback.answer("Лимит пропусков (3) исчерпан", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("practice_exit_"))
async def practice_exit(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["practice_lesson_key"] = None
    set_user_state(user_id, user_state)
    await callback.message.edit_text("Практика прервана. Возвращаюсь к уроку.")
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("lesson_practice_"))
async def lesson_practice_start(callback: CallbackQuery):
    key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    lesson_content = user_state.get("current_lesson", {}).get("content")
    if not lesson_content or "practice_tasks" not in lesson_content:
        await callback.answer("Для этого урока нет заданий", show_alert=True)
        return
    tasks = lesson_content["practice_tasks"]
    # Инициализируем практику
    if "practice" not in user_state:
        user_state["practice"] = {}
    user_state["practice"][key] = {
        "tasks": tasks,
        "completed": [False]*len(tasks),
        "current_session": list(range(min(5, len(tasks)))),  # первые 5 заданий
        "session_index": 0,
        "session_correct": 0,
        "skip_count": 0,
        "attempts": {}
    }
    user_state["practice_lesson_key"] = key
    set_user_state(user_id, user_state)
    await show_practice_task(callback.message, user_id, edit=True)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("practice_hint_"))
async def practice_hint(callback: CallbackQuery):
    lesson_key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    practice = user_state.get("practice", {}).get(lesson_key)
    if not practice:
        await callback.answer("Нет практики")
        return
    idx = practice["session_index"]
    task = practice["tasks"][practice["current_session"][idx]]
    hint = task.get("hint", "Подсказки нет")
    await callback.answer(hint, show_alert=True)

@router.callback_query(lambda c: c.data.startswith("practice_skip_"))
async def practice_skip(callback: CallbackQuery):
    lesson_key = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    practice = user_state.get("practice", {}).get(lesson_key)
    if practice and practice.get("skip_count", 0) < 3:
        practice["skip_count"] += 1
        practice["session_index"] += 1
        set_user_state(user_id, user_state)
        await show_practice_task(callback.message, user_id, edit=True)
        await callback.answer("Задание пропущено")
    else:
        await callback.answer("Лимит пропусков (3) исчерпан", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("practice_exit_"))
async def practice_exit(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_state = get_user_state(user_id)
    user_state["practice_lesson_key"] = None
    set_user_state(user_id, user_state)
    await callback.message.edit_text("Практика прервана. Возвращаюсь к уроку.")
    # здесь можно вызвать back_to_lesson, но проще показать меню
    from handlers.start import show_main_menu
    await show_main_menu(callback.message, edit=True)
    await callback.answer()
# (они у вас были рабочими). Если их нет – дайте знать, я добавлю.

# ========== ОБРАБОТКА ТЕКСТОВЫХ ОТВЕТОВ НА ПРАКТИКУ ==========

def parse_user_answers(text: str, expected_count: int) -> list:
    """Разбивает ответы по запятой, возвращает список длиной expected_count."""
    parts = [part.strip() for part in text.split(',') if part.strip()]
    while len(parts) < expected_count:
        parts.append("")
    return parts[:expected_count]

@router.message(F.text)
async def handle_practice_answer(message: Message):
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    lesson_key = user_state.get("practice_lesson_key")
    if not lesson_key:
        return  # не практика – пропускаем

    practice = user_state.get("practice", {}).get(lesson_key)
    if not practice:
        return

    task_idx = practice.get("session_index", 0)
    tasks = practice.get("tasks", [])
    if task_idx >= len(tasks):
        return

    task = tasks[task_idx]
    subtasks = task.get("subtasks", [])
    expected = len(subtasks)

    # Парсим ответы пользователя
    user_answers = parse_user_answers(message.text, expected)

    correct_count = 0
    feedback_lines = []
    for i, subtask in enumerate(subtasks):
        user_ans = user_answers[i] if i < len(user_answers) else ""
        correct_ans = subtask.get("answer", "").strip()
        # Сравниваем без учёта регистра и лишних пробелов
        if user_ans.lower() == correct_ans.lower():
            correct_count += 1
            feedback_lines.append(f"✅ {subtask['question']} – верно!")
        else:
            feedback_lines.append(
                f"❌ {subtask['question']} – неверно. Правильно: {correct_ans}.\n"
                f"Пояснение: {subtask.get('explanation', '')}"
            )

    # Обновляем статистику сессии
    practice["session_correct"] = practice.get("session_correct", 0) + correct_count
    practice["session_index"] = task_idx + 1
    set_user_state(user_id, user_state)

    # Отправляем обратную связь по заданию
    await message.answer("\n\n".join(feedback_lines))

    # Показываем следующее задание или итог
    await show_practice_task(message, user_id, edit=False)