import csv
import os

CSV_FILENAME = "oxford3000_vocabulary_with_collocations_and_definitions_datasets.csv"
OUTPUT_FILE = "data/words_gold.py"

def read_csv_and_export():
    if not os.path.exists(CSV_FILENAME):
        print("CSV-файл не найден. Запустите скрипт ещё раз, он скачает файл.")
        return

    words_data = {"basic": {"name": "Основной словарь (Oxford 3000)", "words": []}}
    count = 0

    with open(CSV_FILENAME, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # Печатаем реальные заголовки для отладки
        print("Заголовки CSV:", reader.fieldnames)

        for row in reader:
            word = row.get('Word', '').strip()
            if not word:
                continue
            # Берём русский перевод из колонки 'Russian Translation'
            translation = row.get('Russian Translation', '').strip()
            # Определение
            definition = row.get('Definition', '').strip()
            # Часть речи
            part_of_speech = row.get('Part of Speech', '').strip()
            # Пример
            example = row.get('Example Sentence', '').strip()
            # Коллокации
            collocations = row.get('Collocations', '').strip()
            # Синонимы, антонимы — не используем, но можно добавить позже

            words_data["basic"]["words"].append({
                "word": word,
                "trans": translation,
                "part_of_speech": part_of_speech,
                "definition": definition,
                "example": example,
                "collocations": collocations
            })
            count += 1

    # Создаём папку data, если её нет
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    # Записываем в Python-файл
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# data/words_gold.py\n")
        f.write("# Автоматически сгенерировано из CSV\n\n")
        f.write("WORDS_GOLD = {\n")
        for cat, cat_data in words_data.items():
            f.write(f'    "{cat}": {{\n')
            f.write(f'        "name": "{cat_data["name"]}",\n')
            f.write(f'        "words": [\n')
            for w in cat_data["words"]:
                f.write(f'            {{\n')
                f.write(f'                "word": "{escape_string(w["word"])}",\n')
                f.write(f'                "trans": "{escape_string(w["trans"])}",\n')
                f.write(f'                "part_of_speech": "{escape_string(w["part_of_speech"])}",\n')
                f.write(f'                "definition": "{escape_string(w["definition"])}",\n')
                f.write(f'                "example": "{escape_string(w["example"])}",\n')
                f.write(f'                "collocations": "{escape_string(w["collocations"])}",\n')
                f.write(f'            }},\n')
            f.write(f'        ]\n')
            f.write(f'    }},\n')
        f.write("}\n")

    print(f"Готово! Импортировано {count} слов в файл {OUTPUT_FILE}")

def escape_string(s):
    """Экранирует кавычки и переносы строк для корректной записи в Python-файл."""
    if not s:
        return ""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    return s

if __name__ == "__main__":
    read_csv_and_export()