import json
import os
import logging
import traceback
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

TASKS_FILE = os.path.join(os.path.dirname(__file__), "reading_tasks.json")
logger.info(f"Loading reading tasks from: {TASKS_FILE}")


def load_tasks() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Загружает JSON и возвращает структуру:
    {
        "Тип1": {
            "Новичок": [ {...}, ... ],
            "Любитель": [ {...}, ... ],
            "Эксперт": [ {...}, ... ]
        },
        "Тип2": ...
    }
    Если структура не соответствует, логирует ошибку и возвращает пустой словарь.
    """
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info("reading_tasks.json loaded successfully")
            logger.info(f"Top-level keys: {list(data.keys())}")

            # Проверяем структуру: каждый тип должен быть словарём с уровнями
            for type_key, type_value in data.items():
                if not isinstance(type_value, dict):
                    logger.warning(f"Type '{type_key}' is not a dict (got {type(type_value)}). Skipping.")
                    continue
                for level_key, level_value in type_value.items():
                    if not isinstance(level_value, list):
                        logger.warning(f"Level '{level_key}' in type '{type_key}' is not a list. Skipping.")
                        continue
                    logger.info(f"Type '{type_key}', level '{level_key}' has {len(level_value)} tasks")
            return data
    except FileNotFoundError:
        logger.error(f"File not found: {TASKS_FILE}")
        logger.error(traceback.format_exc())
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.error(f"Error at line {e.lineno}, column {e.colno} (char {e.pos})")
        logger.error(traceback.format_exc())
        return {}
    except Exception as e:
        logger.error(f"Unexpected error loading tasks: {e}")
        logger.error(traceback.format_exc())
        return {}


TASKS = load_tasks()


def get_task(type_key: str, level_key: str, index: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает задание по типу, уровню и индексу.
    Если index выходит за границы, возвращает None.
    """
    if not TASKS:
        logger.warning("TASKS is empty, no tasks loaded")
        return None
    type_data = TASKS.get(type_key)
    if not type_data:
        logger.warning(f"Type '{type_key}' not found in TASKS. Available: {list(TASKS.keys())}")
        return None
    level_data = type_data.get(level_key)
    if not level_data:
        logger.warning(f"Level '{level_key}' not found for type '{type_key}'. Available: {list(type_data.keys())}")
        return None
    if not isinstance(level_data, list):
        logger.warning(f"Level data for '{type_key}/{level_key}' is not a list")
        return None
    if index < 0 or index >= len(level_data):
        logger.info(f"Index {index} out of range (0..{len(level_data)-1}) for type '{type_key}', level '{level_key}'")
        return None
    return level_data[index]


def get_task_count(type_key: str, level_key: str) -> int:
    """
    Возвращает количество заданий для данного типа и уровня.
    """
    if not TASKS:
        return 0
    type_data = TASKS.get(type_key)
    if not type_data:
        return 0
    level_data = type_data.get(level_key)
    if not isinstance(level_data, list):
        return 0
    return len(level_data)


def get_levels(type_key: str) -> List[str]:
    """
    Возвращает список доступных уровней для данного типа.
    """
    if not TASKS:
        return []
    type_data = TASKS.get(type_key)
    if not isinstance(type_data, dict):
        return []
    return list(type_data.keys())


def get_all_tasks(type_key: str, level_key: str) -> Optional[List[Dict[str, Any]]]:
    """
    Возвращает весь список заданий для данного типа и уровня.
    """
    if not TASKS:
        return None
    type_data = TASKS.get(type_key)
    if not type_data:
        return None
    level_data = type_data.get(level_key)
    if not isinstance(level_data, list):
        return None
    return level_data