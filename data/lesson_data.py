# data/lesson_data.py

LESSON_CONTENT = {
    # ==================== МОДУЛЬ 1 ====================
    "alphabet": {
        "title": "Алфавит и произношение",
        "pages": [
            {
                "title": "Знакомство с алфавитом",
                "text": """
<b>🔤 Тема: Английский алфавит (26 букв)</b>

<blockquote>Произношение букв в алфавите отличается от их звучания в словах.</blockquote>

<b>A</b> [эй] – Apple<br>
<b>B</b> [би] – Boy<br>
<b>C</b> [си] – Cat<br>
<b>D</b> [ди] – Dog<br>
<b>E</b> [и] – Egg<br>
<b>F</b> [эф] – Fish<br>
<b>G</b> [джи] – Girl<br>
<b>H</b> [эйч] – Hat<br>
<b>I</b> [ай] – Ice<br>
<b>J</b> [джей] – Juice<br>
<b>K</b> [кей] – Kite<br>
<b>L</b> [эл] – Lion<br>
<b>M</b> [эм] – Mother<br>
<b>N</b> [эн] – Night<br>
<b>O</b> [оу] – Orange<br>
<b>P</b> [пи] – Pen<br>
<b>Q</b> [кью] – Queen<br>
<b>R</b> [ар] – Red<br>
<b>S</b> [эс] – Sun<br>
<b>T</b> [ти] – Tea<br>
<b>U</b> [ю] – Umbrella<br>
<b>V</b> [ви] – Violin<br>
<b>W</b> [дабл‑ю] – Window<br>
<b>X</b> [экс] – X‑ray<br>
<b>Y</b> [уай] – Yellow<br>
<b>Z</b> [зед] – Zebra
""",
                "image": None,
                "has_audio_buttons": True
            },
            {
                "title": "Гласные и согласные",
                "text": """
<b>🎵 Гласные (Vowels):</b> A, E, I, O, U (иногда Y)

Остальные – согласные.

<blockquote>Произношение буквы в слове может отличаться от её имени в алфавите.</blockquote>

• <b>A</b> в слове <i>cat</i> – [э]
• <b>E</b> в слове <i>bed</i> – [э]
• <b>I</b> в слове <i>sit</i> – [и]
• <b>O</b> в слове <i>hot</i> – [о]
• <b>U</b> в слове <i>cup</i> – [а]
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Трудные буквы",
                "text": """
<b>⚠️ Буквы, которые путают:</b>

• <b>B [би]</b> и <b>V [ви]</b>
• <b>G [джи]</b> и <b>J [джей]</b>
• <b>W [дабл‑ю]</b> – «двойная U»
• <b>Y [уай]</b> – не [й]
• <b>N [эн]</b> и <b>M [эм]</b>

<blockquote>Совет: повторяйте алфавит вслух 2‑3 минуты в день.</blockquote>
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Практика",
                "text": """
<b>✏️ Задания:</b>
1. Назовите по буквам своё имя (Anna → A, N, N, A)
2. Какая ваша любимая буква? Почему?
3. Напишите 3 слова на каждую из трёх любых букв.
""",
                "image": None,
                "has_audio_buttons": False
            }
        ],
        "faq": [
            {"question": "Почему буквы читаются не так, как в алфавите?", "answer": "Имя буквы и её звук – разные вещи. Звуки выучите позже."}
        ]
    },
    "numbers120": {
        "title": "Числа 1‑20",
        "pages": [
            {
                "title": "1‑10",
                "text": """
<b>🔢 Числа 1‑10:</b><br>
1 one [уан]<br>
2 two [ту]<br>
3 three [сри] (межзубный)<br>
4 four [фо]<br>
5 five [файв]<br>
6 six [сикс]<br>
7 seven [сэвн]<br>
8 eight [эйт]<br>
9 nine [найн]<br>
10 ten [тэн]
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "11‑20",
                "text": """
<b>11‑20:</b><br>
11 eleven [илэвн]<br>
12 twelve [твэлв]<br>
13 thirteen [сётин]<br>
14 fourteen [фотин]<br>
15 fifteen [фифтин]<br>
16 sixteen [сикстин]<br>
17 seventeen [сэвнтин]<br>
18 eighteen [эйтин]<br>
19 nineteen [найн‑тин]<br>
20 twenty [твэнти]
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Правила и советы",
                "text": """
<b>📌 Правила:</b><br>
• 13‑19 = цифра + teen (но 13,15 – исключения)<br>
• Ударение на последний слог (thirTEEN)<br>
• Различайте -teen и -ty (fourTEEN 14 vs FORty 40)<br>
• Forty пишется без 'u'<br>
• В eighteen одна буква 't'<br>
""",
                "image": None,
                "has_audio_buttons": False
            }
        ],
        "faq": [
            {"question": "Разница -teen и -ty?", "answer": "-teen – 'надцать', ударение на окончание; -ty – 'десят', ударение на первый слог."}
        ]
    },
    "tobepositive": {
        "title": "Глагол to be (утверждение)",
        "pages": [
            {
                "title": "Формы to be",
                "text": """
<b>📚 Глагол to be = «быть, находиться»</b><br>
I → <b>am</b><br>
You → <b>are</b><br>
He/She/It → <b>is</b><br>
We → <b>are</b><br>
They → <b>are</b><br>

<b>Примеры:</b><br>
I am a student. (Я студент)<br>
You are my friend.<br>
He is happy.<br>
She is at home.<br>
It is a cat.<br>
We are from Russia.<br>
They are teachers.
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Сокращения",
                "text": """
<b>✂️ Короткие формы:</b><br>
I am → I'm<br>
You are → you're<br>
He is → he's<br>
She is → she's<br>
It is → it's<br>
We are → we're<br>
They are → they're

<blockquote>В кратких утвердительных ответах сокращения НЕЛЬЗЯ: Yes, I am (не I'm)</blockquote>
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Когда использовать",
                "text": """
<b>📌 Случаи:</b><br>
1. Профессия: He is a driver.<br>
2. Место: We are at home.<br>
3. Состояние: I am tired.<br>
4. Возраст: She is 25.<br>
5. Национальность: They are Italian.<br>
6. Описание: The weather is nice.<br>

<b>Запомните:</b> в английском нельзя сказать «I student» – нужен глагол!
""",
                "image": None,
                "has_audio_buttons": False
            }
        ],
        "faq": [
            {"question": "Почему I am, а не I is?", "answer": "Историческая форма. Просто запомните."}
        ]
    },
    "tobenegaquestion": {
        "title": "to be (отрицание и вопрос)",
        "pages": [
            {
                "title": "Отрицание",
                "text": """
<b>🚫 to be + not</b><br>
I am not (I'm not)<br>
You are not (aren't)<br>
He is not (isn't)<br>
She is not (isn't)<br>
It is not (isn't)<br>
We are not (aren't)<br>
They are not (aren't)

<b>Примеры:</b><br>
I am not hungry.<br>
She isn't from Spain.<br>
They aren't at work.
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Вопрос",
                "text": """
<b>❓ to be + подлежащее + ... ?</b><br>
Am I late?<br>
Are you a student?<br>
Is he at home?<br>
Is she happy?<br>
Is it cold?<br>
Are we ready?<br>
Are they from Russia?

<b>Краткие ответы:</b><br>
Yes, I am. / No, I'm not.<br>
Yes, she is. / No, she isn't.
""",
                "image": None,
                "has_audio_buttons": False
            }
        ],
        "faq": [
            {"question": "Почему нельзя Yes, I'm?", "answer": "Сокращение не может стоять в конце предложения."}
        ]
    },
    "countries": {
        "title": "Страны и национальности",
        "pages": [
            {
                "title": "Как спросить",
                "text": """
<b>🌍 Where are you from? – Откуда ты?</b><br>
Ответ: I'm from + страна.<br>
Национальность: I am + национальность.<br>

<b>Примеры:</b><br>
I'm from Russia. I am Russian.<br>
She's from Italy. She is Italian.<br>
They're from Brazil. They are Brazilian.
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Таблица (1)",
                "text": """
<b>Страна → национальность → язык:</b><br>
Russia → Russian → Russian<br>
the USA → American → English<br>
the UK → British → English<br>
Germany → German → German<br>
France → French → French<br>
Italy → Italian → Italian<br>
Spain → Spanish → Spanish<br>
China → Chinese → Chinese<br>
Japan → Japanese → Japanese<br>
Brazil → Brazilian → Portuguese
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Таблица (2)",
                "text": """
Canada → Canadian → English/French<br>
Mexico → Mexican → Spanish<br>
India → Indian → Hindi/English<br>
Australia → Australian → English<br>
Egypt → Egyptian → Arabic<br>
Turkey → Turkish → Turkish<br>
Poland → Polish → Polish<br>
Sweden → Swedish → Swedish<br>
South Korea → Korean → Korean

<b>Суффиксы:</b> -an, -ian, -ese, -ish, -i
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Примеры",
                "text": """
<b>📖 Живые фразы:</b><br>
Tom is from Canada. He is Canadian.<br>
Maria is from Mexico. She speaks Spanish.<br>
We are from China. We are Chinese.<br>
They are from Turkey. They are Turkish.
""",
                "image": None,
                "has_audio_buttons": False
            }
        ],
        "faq": [
            {"question": "Почему British, а не Britain?", "answer": "British – прилагательное; страна – the UK."}
        ]
    },
    "pronouns": {
        "title": "Личные и притяжательные местоимения",
        "pages": [
            {
                "title": "Личные (кто?)",
                "text": """
<b>👤 Личные местоимения (subject):</b><br>
I – я<br>
You – ты/вы<br>
He – он<br>
She – она<br>
It – оно<br>
We – мы<br>
They – они

<b>Примеры:</b><br>
I am a student.<br>
You are my friend.<br>
He is a doctor.<br>
She loves music.<br>
It is raining.<br>
We are happy.<br>
They are from Spain.
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Притяжательные (чей?)",
                "text": """
<b>🔑 Притяжательные (possessive adjectives):</b><br>
I → my (мой)<br>
You → your (твой)<br>
He → his (его)<br>
She → her (её)<br>
It → its (его/её)<br>
We → our (наш)<br>
They → their (их)

<b>Всегда перед существительным:</b><br>
my book, your car, his brother, her phone, its colour, our house, their parents
""",
                "image": None,
                "has_audio_buttons": False
            },
            {
                "title": "Ошибки",
                "text": """
<b>⚠️ Частые ошибки:</b><br>
1. it's (it is) ≠ its (принадлежность)<br>
2. my the book → my book (артикль не нужен)<br>
3. «свой» переводится по подлежащему: She loves her cat.
""",
                "image": None,
                "has_audio_buttons": False
            }
        ],
        "faq": [
            {"question": "Как отличить it's от its?", "answer": "it's = it is. Если можно заменить – пишите с апострофом."}
        ]
    },
    "plural": {
        "title": "Множественное число",
        "pages": [
            {"title": "Правило +s", "text": "a cat → cats, a dog → dogs, a pen → pens"},
            {"title": "Окончание -es", "text": "bus → buses, box → boxes, watch → watches (после sh, ch, s, ss, x, z)"},
            {"title": "Y → I + es", "text": "baby → babies, city → cities (согласная + y), но boy → boys (гласная + y)"},
            {"title": "Исключения", "text": "man → men, woman → women, child → children, tooth → teeth, foot → feet, person → people, fish → fish, sheep → sheep"}
        ],
        "faq": [{"question": "Произношение -s?", "answer": "[s] после глухих, [z] после звонких, [ɪz] после шипящих."}]
    },
    "questionwords": {
        "title": "Вопросительные слова",
        "pages": [
            {"title": "What / Where", "text": "What? – Что? Какой?\nWhat is your name?\nWhere? – Где? Куда?\nWhere are you from?"},
            {"title": "Who / How", "text": "Who? – Кто?\nWho is she?\nHow? – Как?\nHow are you? How old are you?"},
            {"title": "Why / When / Which / Whose", "text": "Why? – Почему?\nWhen? – Когда?\nWhich? – Который?\nWhose? – Чей?"},
            {"title": "How much / how many", "text": "How much – для неисчисляемых (money, water)\nHow many – для исчисляемых (apples, people)"}
        ],
        "faq": [{"question": "Разница much/many?", "answer": "Much – неисчисляемые, many – исчисляемые."}]
    },
    "thereisare": {
        "title": "There is / There are",
        "pages": [
            {"title": "Утверждение", "text": "There is a book on the table.\nThere are two chairs."},
            {"title": "Отрицание и вопрос", "text": "There isn't a pen.\nIs there a bank?"},
            {"title": "Примеры", "text": "There is a park near my house.\nThere are many people at the party."}
        ],
        "faq": [{"question": "Можно ли there have?", "answer": "Нет, только there is/are."}]
    },
    "prepositionsplace": {
        "title": "Предлоги места",
        "pages": [
            {"title": "Базовые", "text": "in (в), on (на), under (под), behind (за), next to (рядом), between (между), opposite (напротив)"},
            {"title": "Примеры", "text": "The cat is under the table.\nThe bank is next to the post office.\nThe park is between the school and the hospital."}
        ],
        "faq": [{"question": "Разница next to / beside?", "answer": "Одинаковы, beside формальнее."}]
    },
    "adjectives": {
        "title": "Прилагательные",
        "pages": [
            {"title": "Описание", "text": "red, blue, big, small, happy, sad, good, bad, nice, beautiful, easy, difficult"},
            {"title": "Порядок", "text": "a nice big house (мнение → размер → цвет). После глагола to be: The house is big."},
            {"title": "Сравнение", "text": "big → bigger → the biggest (короткие); beautiful → more beautiful → the most beautiful (длинные). Исключения: good → better → best, bad → worse → worst."}
        ],
        "faq": [{"question": "Как выбрать -er или more?", "answer": "Односложные и двусложные на -y, -er, -le, -ow: -er. Остальные: more."}]
    },
    "presentsimple": {
        "title": "Present Simple",
        "pages": [
            {"title": "Утверждение", "text": "I/You/We/They + V\nHe/She/It + V‑s\nI work. He works."},
            {"title": "Отрицание и вопрос", "text": "Don't/Doesn't + V\nDo/Does + подлежащее + V?\nI don't like coffee.\nDoes she speak English?"},
            {"title": "Маркеры", "text": "always, usually, often, sometimes, never, every day, on Mondays"}
        ],
        "faq": [{"question": "Почему -s у глагола, а не у to be?", "answer": "To be – исключение. Остальные глаголы работают по правилу."}]
    },
    # ==================== МОДУЛЬ 1 (уроки 1–12 уже даны) ====================

# ==================== МОДУЛЬ 2 ====================
    "prescont": {
        "title": "Present Continuous (действие сейчас)",
        "pages": [
            {"title": "Образование", "text": "am/is/are + V‑ing\nI am playing. She is reading. They are eating."},
            {"title": "Отрицание и вопрос", "text": "I am not sleeping. Are you listening? Yes, I am. / No, I'm not."},
            {"title": "Когда использовать", "text": "1. Действие прямо сейчас: Look! It is raining.\n2. Временная ситуация: I am living in London this month.\n3. План на ближайшее будущее: I am meeting my friend tomorrow."},
            {"title": "Маркеры", "text": "now, at the moment, today, this week, Listen!, Look!"}
        ],
        "faq": [{"question": "Глаголы, не употребляющиеся в Continuous?", "answer": "want, know, understand, like, love, hate, see, hear – чувства, мысли, восприятие."}]
    },
    "presimplevscont": {
        "title": "Present Simple vs Present Continuous",
        "pages": [
            {"title": "Разница", "text": "Simple – регулярные действия, факты, расписание.\nContinuous – прямо сейчас, временно, планы."},
            {"title": "Примеры", "text": "I work every day. (рутина)\nI am working now. (сейчас)\nShe speaks French. (факт)\nShe is speaking French right now."}
        ],
        "faq": [{"question": "Как не путать?", "answer": "Смотрите на маркеры: always, usually, every day -> Simple; now, at the moment -> Continuous."}]
    },
    "tobePast": {
        "title": "Глагол to be в прошедшем времени (was/were)",
        "pages": [
            {"title": "Формы", "text": "I/he/she/it – was\nyou/we/they – were\nI was at home. They were happy."},
            {"title": "Отрицание и вопрос", "text": "was not (wasn't), were not (weren't)\nWas he a doctor? Were you tired?"}
        ],
        "faq": [{"question": "Разница was/were?", "answer": "Was для единственного числа (кроме you), were для множественного и you."}]
    },
    "pastSimpleRegular": {
        "title": "Past Simple (правильные глаголы)",
        "pages": [
            {"title": "Образование", "text": "V + -ed\nwork → worked, play → played, watch → watched"},
            {"title": "Произношение -ed", "text": "[t] после глухих: worked\n[d] после звонких: played\n[ɪd] после t/d: wanted, needed"},
            {"title": "Отрицание и вопрос", "text": "did not (didn't) + V\nDid you work yesterday? Yes, I did. / No, I didn't."}
        ],
        "faq": [{"question": "Почему wanted произносится как wantid?", "answer": "После t/d добавляется слог [ɪd]."}]
    },
    "pastSimpleIrregular": {
        "title": "Past Simple (неправильные глаголы)",
        "pages": [
            {"title": "Основные 10", "text": "go → went, see → saw, have → had, eat → ate, drink → drank, buy → bought, meet → met, read → read, write → wrote, speak → spoke"},
            {"title": "Примеры", "text": "I went to school yesterday. She saw a film. We had lunch at 1."}
        ],
        "faq": [{"question": "Как учить?", "answer": "Группируйте по рифме: sing‑sang‑sung, drink‑drank‑drunk."}]
    },
    "futureGoingTo": {
        "title": "Конструкция to be going to (планы)",
        "pages": [
            {"title": "Утверждение", "text": "am/is/are + going to + V\nI am going to study. She is going to travel."},
            {"title": "Отрицание и вопрос", "text": "I am not going to stay. Are you going to call him?"},
            {"title": "Когда использовать", "text": "1. Планы: We are going to visit Paris.\n2. Предсказания по фактам: Look at those clouds! It is going to rain."}
        ],
        "faq": [{"question": "Разница will и going to?", "answer": "Going to – планы и предсказания по фактам; will – спонтанные решения."}]
    },
    "modalCan": {
        "title": "Модальный глагол can (уметь, мочь)",
        "pages": [
            {"title": "Формы", "text": "I can swim. She can dance. (без to)\nОтрицание: cannot / can't\nВопрос: Can you help me?"},
            {"title": "Значения", "text": "1. Способность: He can play piano.\n2. Разрешение: You can go now.\n3. Просьба: Can I open the window?"}
        ],
        "faq": [{"question": "Как спросить разрешение?", "answer": "Can I...? / Could I...? (вежливее)"}]
    },
    "modalMust": {
        "title": "Модальный глагол must (должен)",
        "pages": [
            {"title": "Формы", "text": "I must study. (без to)\nОтрицание: must not / mustn't\nВопрос: Must we go now?"},
            {"title": "Значения", "text": "1. Обязанность: You must wear a seatbelt.\n2. Настоятельная рекомендация: You must see that film.\n3. Запрет (mustn't): You mustn't smoke here."}
        ],
        "faq": [{"question": "Разница must и have to?", "answer": "Must – личное чувство долга; have to – вынужден из-за обстоятельств."}]
    },
    "ordinalNumbers": {
        "title": "Порядковые числительные",
        "pages": [
            {"title": "1‑10", "text": "1st first, 2nd second, 3rd third, 4th fourth, 5th fifth, 6th sixth, 7th seventh, 8th eighth, 9th ninth, 10th tenth"},
            {"title": "Правила", "text": "Обычно +th (four→fourth), исключения: one→first, two→second, three→third, five→fifth, eight→eighth, nine→ninth, twelve→twelfth."}
        ],
        "faq": [{"question": "Как сказать дату?", "answer": "The fifth of May или May fifth."}]
    },
    "adverbsFrequency": {
        "title": "Наречия частотности",
        "pages": [
            {"title": "Список", "text": "always (100%), usually, often, sometimes, rarely, never (0%)"},
            {"title": "Место в предложении", "text": "Перед основным глаголом: I often play tennis.\nПосле to be: She is always late."}
        ],
        "faq": [{"question": "Разница sometimes/usually?", "answer": "Sometimes – иногда (30-40%), usually – обычно (80-90%)."}]
    },
    "prepositionsTime": {
        "title": "Предлоги времени (at, in, on)",
        "pages": [
            {"title": "Правила", "text": "at + время (at 5 o'clock)\non + день недели/дата (on Monday, on May 5th)\nin + месяц/год/часть дня (in July, in 2025, in the morning)"},
            {"title": "Исключения", "text": "at night, at the weekend, in the morning/afternoon/evening, on time, at the moment."}
        ],
        "faq": [{"question": "Почему at night, но in the evening?", "answer": "Устойчивые выражения, нужно запомнить."}]
    },
    "foodVocabulary": {
        "title": "Лексика: еда и напитки",
        "pages": [
            {"title": "Продукты", "text": "fruit, vegetables, meat, fish, bread, rice, pasta, eggs, milk, cheese, butter, sugar, salt, oil, juice, water, coffee, tea"},
            {"title": "Приёмы пищи", "text": "breakfast, lunch, dinner, snack, dessert"},
            {"title": "Глаголы", "text": "eat, drink, cook, bake, fry, boil, cut, mix, taste, enjoy"}
        ],
        "faq": [{"question": "Исчисляемые/неисчисляемые?", "answer": "Неисчисляемые: milk, water, sugar, rice, bread. Исчисляемые: apple, egg, banana, carrot."}]
    },
    "countableUncountable": {
        "title": "Исчисляемые и неисчисляемые существительные",
        "pages": [
            {"title": "Исчисляемые", "text": "Можно посчитать: an apple, two apples. Используют a/an, many, few."},
            {"title": "Неисчисляемые", "text": "Нельзя посчитать: water, milk, sugar. Используют some, much, little."},
            {"title": "Слова-помощники", "text": "some (утверждение), any (отрицание/вопрос), a lot of (много), how much/many (сколько)."}
        ],
        "faq": [{"question": "Как спросить количество?", "answer": "How many apples? How much water?"}]
    },
    "clothesVocabulary": {
        "title": "Лексика: одежда",
        "pages": [
            {"title": "Виды", "text": "shirt, T‑shirt, blouse, sweater, jacket, coat, trousers, jeans, shorts, skirt, dress, socks, shoes, boots, trainers, hat, cap, scarf, gloves"},
            {"title": "Глаголы", "text": "wear, put on, take off, buy, try on, fit, suit"}
        ],
        "faq": [{"question": "Обувь: shoe или shoes?", "answer": "Обычно во множественном: shoes, boots. 'A shoe' – одна туфля."}]
    },
    "weatherVocabulary": {
        "title": "Лексика: погода",
        "pages": [
            {"title": "Прилагательные", "text": "sunny, rainy, cloudy, snowy, windy, foggy, hot, warm, cool, cold"},
            {"title": "Глаголы и выражения", "text": "It is + прилагательное: It is sunny.\nIt is + V‑ing: It is raining.\nThere is + существительное: There is fog."}
        ],
        "faq": [{"question": "Как спросить о погоде?", "answer": "What's the weather like today? / How is the weather?"}]
    },
    "dailyRoutine": {
        "title": "Режим дня",
        "pages": [
            {"title": "Глаголы", "text": "wake up, get up, brush teeth, have a shower, get dressed, have breakfast, go to school/work, have lunch, do homework, watch TV, have dinner, go to bed"},
            {"title": "Пример рассказа", "text": "I wake up at 7. I have breakfast at 7:30. I go to work at 8. I have lunch at 1. I come home at 6. I have dinner at 7. I go to bed at 11."}
        ],
        "faq": [{"question": "Как спросить о времени действий?", "answer": "What time do you wake up? / When do you go to work?"}]
    },
    "familyVocabulary": {
        "title": "Лексика: семья",
        "pages": [
            {"title": "Члены семьи", "text": "mother, father, parents, sister, brother, son, daughter, grandmother, grandfather, grandparents, aunt, uncle, cousin, niece, nephew, wife, husband"},
            {"title": "Пример", "text": "My family: mother Anna, father John, sister Kate, brother Tom. I have two cousins."}
        ],
        "faq": [{"question": "Как отличить niece от nephew?", "answer": "Niece – племянница, nephew – племянник."}]
    },
    "houseVocabulary": {
        "title": "Лексика: дом и комната",
        "pages": [
            {"title": "Комнаты", "text": "living room, bedroom, kitchen, bathroom, dining room, hall, study, garage, garden, balcony"},
            {"title": "Мебель", "text": "bed, sofa, table, chair, cupboard, wardrobe, desk, shelf, lamp, curtain, carpet, mirror, fridge, cooker, sink, bath, shower, toilet"}
        ],
        "faq": [{"question": "Ванная: bathroom или restroom?", "answer": "Bathroom – в доме, restroom – в общественных местах."}]
    },
    "townVocabulary": {
        "title": "Лексика: город",
        "pages": [
            {"title": "Места", "text": "bank, supermarket, shop, pharmacy, hospital, clinic, school, university, library, cinema, theatre, museum, park, square, bus station, railway station, airport, hotel, restaurant, cafe, post office, police station, fire station"}
        ],
        "faq": [{"question": "Как спросить дорогу?", "answer": "Excuse me, where is the bank? / How can I get to the station?"}]
    },
    "directions": {
        "title": "Как спросить и объяснить дорогу",
        "pages": [
            {"title": "Вопросы", "text": "Where is the nearest pharmacy?\nCan you tell me the way to the museum?\nHow far is the station?"},
            {"title": "Ответы", "text": "Go straight. Turn left/right. Cross the street. It's opposite the park. It's next to the bank. It's on the corner."}
        ],
        "faq": [{"question": "Что значит 'on the corner'?", "answer": "На углу."}]
    },
    "jobVocabulary": {
        "title": "Лексика: профессии",
        "pages": [
            {"title": "Профессии", "text": "doctor, nurse, teacher, student, engineer, driver, waiter, waitress, cook, shop assistant, manager, secretary, cleaner, lawyer, police officer, firefighter, pilot, flight attendant, artist, musician, writer"}
        ],
        "faq": [{"question": "Как сказать 'кем вы работаете'?", "answer": "What do you do? I am a teacher."}]
    },
    "hobbyVocabulary": {
        "title": "Лексика: хобби и свободное время",
        "pages": [
            {"title": "Хобби", "text": "reading, writing, drawing, painting, photography, cooking, baking, gardening, hiking, camping, fishing, swimming, running, cycling, playing football, playing chess, listening to music, watching films, playing video games, travelling"},
            {"title": "Глаголы", "text": "I like + V‑ing. I enjoy reading. I am interested in art."}
        ],
        "faq": [{"question": "Как спросить о хобби?", "answer": "What do you like doing in your free time?"}]
    },
    "holidayVocabulary": {
        "title": "Лексика: отпуск и путешествия",
        "pages": [
            {"title": "Слова", "text": "travel, trip, journey, holiday, vacation, tourist, guide, hotel, hostel, campsite, luggage, suitcase, ticket, passport, visa, flight, airport, train, bus, car, ship, cruise, beach, mountain, lake, forest"},
            {"title": "Глаголы", "text": "go on holiday, book a hotel, pack a suitcase, catch a flight, stay in a hotel, visit a museum, take photos, swim in the sea, climb a mountain"}
        ],
        "faq": [{"question": "Разница travel/trip/journey?", "answer": "Travel – путешествие вообще, trip – поездка (туда-обратно), journey – путь в одну сторону."}]
    },
    "shoppingVocabulary": {
        "title": "Лексика: покупки",
        "pages": [
            {"title": "Фразы", "text": "How much is it? How much does it cost? Can I try it on? Do you have this in a different colour/size? I'll take it. Can I pay by card? Here's the money."},
            {"title": "Магазины", "text": "supermarket, department store, clothes shop, shoe shop, bookshop, pharmacy, bakery, butcher's, greengrocer's, electronics shop"}
        ],
        "faq": [{"question": "Скидка – discount или sale?", "answer": "Discount – скидка, sale – распродажа."}]
    },
    "bodyVocabulary": {
        "title": "Лексика: тело человека",
        "pages": [
            {"title": "Части тела", "text": "head, face, hair, eye, ear, nose, mouth, tooth, tongue, neck, shoulder, arm, elbow, hand, finger, chest, back, stomach, hip, leg, knee, foot, toe, skin, bone, muscle"},
            {"title": "Глаголы", "text": "hurt, ache, break, cut, wash, brush, comb, shave, exercise, sleep, breathe, eat, drink, see, hear, smell, touch"}
        ],
        "faq": [{"question": "Tooth или teeth?", "answer": "Tooth – зуб (ед.), teeth – зубы (мн.)."}]
    }
}
}