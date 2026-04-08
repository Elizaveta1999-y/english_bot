from collections import Counter
from services.openai import chat
import time

games = {}

def start(user_id):
    base = "education"

    games[user_id] = {
        "base": base,
        "words": [],
        "start": time.time(),
        "limit": 300
    }

    return base


def valid(word, base):
    return not (Counter(word) - Counter(base))


async def add_word(message):
    user_id = message.from_user.id
    g = games[user_id]

    if time.time() - g["start"] > g["limit"]:
        await finish(message)
        return

    w = message.text.lower()

    if len(w) < 3:
        await message.answer("Минимум 3 буквы")
        return

    if not valid(w, g["base"]):
        await message.answer("❌ Нельзя")
        return

    if w in g["words"]:
        await message.answer("Уже было")
        return

    g["words"].append(w)
    await message.answer(f"✅ {w}")


async def finish(message):
    user_id = message.from_user.id
    g = games[user_id]

    prompt = f"""
Words: {g['words']}
Analyze like duolingo:
mistakes, level, advice
"""

    result = chat(prompt)

    await message.answer(
        f"Время вышло!\nТы написал {len(g['words'])} слов\n\n{result}"
    )

    del games[user_id]