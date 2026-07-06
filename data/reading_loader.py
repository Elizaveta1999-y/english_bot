import json
import os
import logging
import traceback

logger = logging.getLogger(__name__)

TASKS_FILE = os.path.join(os.path.dirname(__file__), "reading_tasks.json")
logger.info(f"Loading reading tasks from: {TASKS_FILE}")

def load_tasks():
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info("reading_tasks.json loaded successfully")
            logger.info(f"Keys: {list(data.keys())}")
            for type_key, levels in data.items():
                for level_key, tasks in levels.items():
                    logger.info(f"Type '{type_key}', level '{level_key}' has {len(tasks)} tasks")
            return data
    except FileNotFoundError:
        logger.error(f"File not found: {TASKS_FILE}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        # Подробный вывод с номером строки и позицией
        error_msg = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_msg}")
        # Также выводим информацию из объекта ошибки
        logger.error(f"Error at line {e.lineno}, column {e.colno} (char {e.pos})")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error loading tasks: {e}")
        logger.error(traceback.format_exc())
        return {}

TASKS = load_tasks()

def get_task(type_key: str, level_key: str, index: int):
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
    if index < 0 or index >= len(level_data):
        logger.warning(f"Index {index} out of range (0..{len(level_data)-1}) for type '{type_key}', level '{level_key}'")
        return None
    return level_data[index]