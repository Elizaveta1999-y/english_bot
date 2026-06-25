import os
import re

data_dir = "data"
for filename in os.listdir(data_dir):
    if filename.endswith(".py"):
        path = os.path.join(data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Заменяем целые слова (не внутри кавычек)
        content = re.sub(r'\btrue\b', 'True', content)
        content = re.sub(r'\bfalse\b', 'False', content)
        content = re.sub(r'\bnull\b', 'None', content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Обработан {filename}")