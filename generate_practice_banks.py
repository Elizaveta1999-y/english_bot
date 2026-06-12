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

# Загрузка API ключа из .env (если используете)
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
# Для A1 и A2
NORMAL_A1A2 = 40
STAR_A1A2 = 20
# Для остальных уровней (B1, B2, C1, C2, thematic)
NORMAL_OTHER = 60
STAR_OTHER = 20

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

def call_deepseek(prompt: str, max_tokens=3500, temperature=0.6) -> str:
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

def generate_tasks(topic_name: str, topic_key: str, normal_count: int, star_count: int) -> List[Dict]:
    # Разбиваем на две части (по половине)
    half_normal = normal_count // 2
    half_star = star_count // 2
    # Первая часть
    tasks1 = _generate_batch(topic_name, topic_key, half_normal, half_star)
    # Вторая часть (остаток, если нечётное количество)
    remaining_normal = normal_count - half_normal
    remaining_star = star_count - half_star
    tasks2 = _generate_batch(topic_name, topic_key, remaining_normal, remaining_star) if remaining_normal > 0 else []
    # Объединяем
    return tasks1 + tasks2

def _generate_batch(topic_name: str, topic_key: str, normal_count: int, star_count: int) -> List[Dict]:
    prompt = f"""
Ты генератор учебных заданий по английскому языку.
Создай {normal_count} обычных заданий и {star_count} заданий со звёздочкой (*) для темы "{topic_name}" (ключ: {topic_key}).

Верни ТОЛЬКО JSON-массив. Начинай с '[' и заканчивай ']'. Никаких пояснений. Используй двойные кавычки.

Формат каждого объекта:
{{"type": "fill_blank"/"reorder"/"translation"/"choice"/"open",
 "text": "...",
 "correct": "...",
 "hint": "...",
 "star": true/false,
 (только для choice) "options": ["...","..."] }}
"""
    raw = call_deepseek(prompt, max_tokens=2000, temperature=0.5)
    # Ищем JSON
    start = raw.find('[')
    end = raw.rfind(']')
    if start == -1 or end == -1:
        print(f"  Не найден JSON для {topic_key} (batch)")
        return []
    json_str = raw[start:end+1]
    import re
    # Удаляем лишние запятые перед скобками
    json_str = re.sub(r',\s*]', ']', json_str)
    json_str = re.sub(r',\s*}', '}', json_str)
    try:
        tasks = json.loads(json_str)
        if not isinstance(tasks, list):
            tasks = []
    except Exception as e:
        print(f"  Ошибка парсинга batch: {e}")
        with open(f"debug_{topic_key}_batch.txt", "w", encoding="utf-8") as f:
            f.write(json_str)
        return []
    for t in tasks:
        t.setdefault("star", False)
        t.setdefault("hint", "")
    return tasks

def update_file(filepath: str, normal_count: int):
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
    exec(content, namespace)
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

    # Перебираем уроки
    for key, lesson_data in lessons_dict.items():
        if "practice_tasks" in lesson_data:
            print(f"  Урок {key} уже имеет practice_tasks, пропускаем")
            continue
        topic_title = lesson_data.get("title", key)
        print(f"  Генерация для {key} ({topic_title})...")
        star_count = STAR_A1A2 if filepath in ["data/level_a1.py", "data/level_a2.py"] else STAR_OTHER
        tasks = generate_tasks(topic_title, key, normal_count, star_count)
        if tasks and len(tasks) >= 5:
            lesson_data["practice_tasks"] = tasks
            print(f"    Сгенерировано {len(tasks)} заданий")
        else:
            print(f"    Ошибка: получено {len(tasks)} заданий, пропускаем")
        time.sleep(1)  # пауза между запросами

    # Запись обновлённого словаря обратно
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"{var_name} = ")
        json_str = json.dumps(lessons_dict, indent=2, ensure_ascii=False)
        json_str = json_str.replace('null', 'None')
        f.write(f"{var_name} = " + json_str)
    print(f"  Файл обновлён")

def main():
    for filepath in LESSON_FILES:
        if not os.path.exists(filepath):
            print(f"Файл не найден: {filepath}")
            continue
        normal_count = FILE_CONFIG.get(filepath, NORMAL_OTHER)
        update_file(filepath, normal_count)
    print("\nГенерация завершена.")

if __name__ == "__main__":
    main()