import os
import re

data_dir = "data"
for filename in os.listdir(data_dir):
    if filename.endswith(".py") and filename not in ["users.py"]:
        path = os.path.join(data_dir, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Удаляем все блоки "practice_tasks": [...]
        new_content = re.sub(r'"practice_tasks":\s*\[[^\]]*\]', '"practice_tasks": []', content, flags=re.DOTALL)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Очищено: {filename}")
print("Готово!")