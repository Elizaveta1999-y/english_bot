import json
import os

file_path = 'data/reading_tasks.json'
if not os.path.exists(file_path):
    print("Файл не найден!")
else:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        print("Ключи:", list(data.keys()))