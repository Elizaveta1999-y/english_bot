import json
import os

TASKS_FILE = os.path.join(os.path.dirname(__file__), "reading_tasks.json")

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

TASKS = load_tasks()

def get_task(type_key: str, level_key: str, index: int):
    """
    Возвращает задание по типу, уровню и индексу.
    Если индекс выходит за границы, возвращает None.
    """
    type_data = TASKS.get(type_key)
    if not type_data:
        return None
    level_data = type_data.get(level_key)
    if not level_data:
        return None
    if index < 0 or index >= len(level_data):
        return None
    return level_data[index]

def load_tasks():
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        print("DEBUG: loaded reading_tasks.json, keys:", list(data.keys()))
        return data