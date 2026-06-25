#!/usr/bin/env python3
"""
Генерация банков заданий для всех уроков.
Запуск: python generate_practice_banks.py
"""

import os
import sys
import json
import re
import shutil
import time
from typing import Dict, List, Any

# Добавьте путь к проекту (если запускаете не из корня)
sys.path.append(os.path.dirname(__file__))

# Загрузка API ключа из .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEEPSEEK_API_KEY = "sk-652dc7c7679d49268bc1ebf9b725b0bb"
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY не найден. Установите переменную окружения или добавьте в .env")

import requests

# ----- НАСТРОЙКИ -----
NORMAL_A1A2 = 20   # 20 обычных заданий на урок (2 на вариант × 10 вариантов)
STAR_A1A2 = 10     # 10 звёздочных (1 на вариант × 10 вариантов)
NORMAL_OTHER = 20
STAR_OTHER = 10

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

# Файлы для обработки (порядок важен)
LESSON_FILES = [
    "data/level_a1.py",
    "data/level_a2.py",
    "data/level_b1.py",
    "data/level_b2.py",
    "data/level_c1.py",
    "data/level_c2.py",
    "data/thematic_new.py",
]

# Соответствие файла -> количество обычных заданий
FILE_CONFIG = {
    "data/level_a1.py": NORMAL_A1A2,
    "data/level_a2.py": NORMAL_A1A2,
    "data/level_b1.py": NORMAL_OTHER,
    "data/level_b2.py": NORMAL_OTHER,
    "data/level_c1.py": NORMAL_OTHER,
    "data/level_c2.py": NORMAL_OTHER,
    "data/thematic_new.py": NORMAL_OTHER,
}

def call_deepseek(prompt: str, max_tokens=4000, temperature=0.6) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    for attempt in range(3):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  Ошибка API (попытка {attempt+1}): {e}")
            time.sleep(2 ** attempt)
    return ""

def generate_tasks_for_topic(topic_name: str, topic_key: str, level_hint: str = "") -> List[Dict]:
    """
    Генерирует 3 комплексных задания для одного урока (10 подвопросов каждое).
    Третье задание получает star: true.
    """
    # Определяем язык инструкций и название заданий по уровню
    if level_hint.upper() in ["A1", "A2", "B1"]:
        lang = "ru"
        task_name = "Задание"
        instruction_lang = "на русском"
    else:
        lang = "en"
        task_name = "Exercise"
        instruction_lang = "in English"

    prompt = f"""
Ты — опытный преподаватель английского языка. Ты создаёшь учебные задания для учеников.

Тема урока: "{topic_name}" (ключ: {topic_key}, уровень: {level_hint}).

Твоя задача — создать ровно 3 КОМПЛЕКСНЫХ задания для этой темы. Каждое задание должно содержать 10 подвопросов.

**Важно:** Третье задание должно быть ДРУГОГО ТИПА, чем первые два, чтобы разнообразить практику. Но все 3 задания должны иметь однозначный правильный ответ (не творческие).

**Рекомендации по типам заданий:**

1. Для грамматических тем (времена, модальные глаголы, пассив, артикли):
   - Задание 1: Вставьте правильную форму/слово (fill_blank)
   - Задание 2: Переведите предложения с русского на английский (translation)
   - Задание 3: Составьте предложения из слов в правильном порядке (reorder)

2. Для лексических тем (еда, одежда, профессии, дом, город):
   - Задание 1: Вставьте пропущенные буквы (fill_blank)
   - Задание 2: Выберите правильное слово из списка (choice или fill_blank)
   - Задание 3: Переведите предложения на английский (translation)

3. Для тем с числами, алфавитом, порядковыми числительными:
   - Задание 1: Напишите по описанию
   - Задание 2: Расставьте по порядку
   - Задание 3: Переведите с русского на английский

**Важно:** третье задание должно отличаться по типу от первых двух, но иметь чёткий правильный ответ (поле "answer").

**Общие требования:**
- Все 3 задания — комплексные (по 10 подвопросов).
- Для каждого подвопроса укажи поле "explanation" (краткое пояснение правильного ответа {instruction_lang}).
- Язык инструкций: для A1–B1 — русский; для B2–C2 и thematic — английский.
- Названия заданий: для A1–B1 — «Задание 1», «Задание 2», «Задание 3»; для остальных — «Exercise 1», «Exercise 2», «Exercise 3».

**Формат вывода:** верни ТОЛЬКО JSON-массив из 3 заданий. Без пояснений, без markdown.

Пример правильного формата (для темы "Present Simple", уровень A1):
[
  {{
    "type": "complex",
    "text": "Задание 1. Вставьте глагол в правильной форме (Present Simple).\\n\\n1. I ___ (go) to school every day.\\n2. She ___ (read) books in the evening.\\n... (10 вопросов)",
    "subtasks": [
      {{"question": "I ___ (go) to school every day.", "answer": "go", "explanation": "I + go (без -s)"}},
      ...
    ]
  }},
  {{
    "type": "complex",
    "text": "Задание 2. Переведите предложения на английский (Present Simple).\\n\\n1. Я хожу в школу каждый день.\\n2. Она читает книги по вечерам.\\n... (10 предложений)",
    "subtasks": [
      {{"question": "Я хожу в школу каждый день.", "answer": "I go to school every day.", "explanation": "I go to school every day."}},
      ...
    ]
  }},
  {{
    "type": "complex",
    "text": "Задание 3. Составьте предложения из слов (Present Simple).\\n\\n1. go / I / school / to / every / day\\n2. reads / books / in / she / evening / the\\n... (10 предложений)",
    "subtasks": [
      {{"question": "go / I / school / to / every / day", "answer": "I go to school every day.", "explanation": "Порядок: подлежащее + глагол + дополнение"}},
      ...
    ]
  }}
]
"""
    raw = call_deepseek(prompt, max_tokens=4000, temperature=0.6)
    # Ищем JSON
    start = raw.find('[')
    end = raw.rfind(']')
    if start == -1 or end == -1:
        print(f"  Не найден массив JSON для {topic_key}")
        return []
    json_str = raw[start:end+1]
    # Удаляем лишние запятые
    json_str = re.sub(r',\s*]', ']', json_str)
    json_str = re.sub(r',\s*}', '}', json_str)
    try:
        tasks = json.loads(json_str)
        if not isinstance(tasks, list):
            tasks = []
    except Exception as e:
        print(f"  Ошибка парсинга JSON: {e}")
        with open(f"debug_{topic_key}.txt", "w", encoding="utf-8") as f:
            f.write(json_str)
        return []
    # Третье задание (индекс 2) получает star: true
    for i, t in enumerate(tasks):
        t.setdefault("star", i == 2)
        t.setdefault("hint", "")
    return tasks

def update_file(filepath: str, normal_count: int, star_count: int):
    """Обрабатывает один файл, добавляя practice_bank для уроков, где его нет"""
    print(f"\nОбработка {filepath} (нормальных заданий: {normal_count})")
    # Резервная копия
    backup = filepath + ".bak"
    shutil.copy2(filepath, backup)
    print(f"  Резервная копия: {backup}")

    # Читаем содержимое
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Определяем имя переменной словаря
    namespace = {}
    # Заменяем null на None при чтении
    content_fixed = content.replace('null', 'None').replace('true', 'True').replace('false', 'False')
    exec(content_fixed, namespace)
    possible_names = ["LEVEL_A1_CONTENT", "LEVEL_A2_CONTENT", "LEVEL_B1_CONTENT",
                      "LEVEL_B2_CONTENT", "LEVEL_C1_CONTENT", "LEVEL_C2_CONTENT",
                      "THEMATIC_NEW_CONTENT"]
    var_name = None
    for name in possible_names:
        if name in namespace:
            var_name = name
            break
    if not var_name:
        print(f"  Не найдена переменная-словарь в {filepath}")
        return
    lessons_dict = namespace[var_name]

    # Определяем уровень для файла
    level_hint = os.path.basename(filepath).replace(".py", "").replace("level_", "").upper()
    if level_hint == "THEMATIC_NEW":
        level_hint = "C1"

    # Перебираем уроки
    for key, lesson_data in lessons_dict.items():
        # Пропускаем, если уже есть практика
                # Если есть только practice_tasks (старая), удаляем её и генерируем новую
        if "practice_tasks" in lesson_data and "practice_bank" not in lesson_data:
            print(f"  Урок {key} имеет старую practice_tasks, удаляем и генерируем новую")
            del lesson_data["practice_tasks"]
        elif "practice_bank" in lesson_data:
            print(f"  Урок {key} уже имеет practice_bank, пропускаем")
            continue
        topic_title = lesson_data.get("title", key)
        print(f"  Генерация для {key} ({topic_title})...")
        tasks = generate_tasks_for_topic(topic_title, key, level_hint)
        if tasks and len(tasks) == 3:
            # Превращаем 3 задания в 1 вариант (в формате practice_bank)
            lesson_data["practice_bank"] = [tasks]
            print(f"    Сгенерировано 3 задания (1 вариант)")
        else:
            print(f"    Ошибка: получено {len(tasks)} заданий, пропускаем")
        time.sleep(1)  # пауза между запросами

    # Запись обновлённого словаря обратно
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"{var_name} = ")
        json_str = json.dumps(lessons_dict, indent=2, ensure_ascii=False)
        json_str = json_str.replace('null', 'None')
        f.write(json_str)
    print(f"  Файл обновлён")

def main():
    for filepath in LESSON_FILES:
        if not os.path.exists(filepath):
            print(f"Файл не найден: {filepath}")
            continue
        normal_count = FILE_CONFIG.get(filepath, NORMAL_OTHER)
        star_count = STAR_A1A2 if filepath in ["data/level_a1.py", "data/level_a2.py"] else STAR_OTHER
        update_file(filepath, normal_count, star_count)
    print("\nГенерация завершена.")

if __name__ == "__main__":
    main()