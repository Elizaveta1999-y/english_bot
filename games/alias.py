from services.voice import tts
from services.openai import chat
import random

alias_games = {}


def start_alias(user_id):
    words = [
        ("apple","яблоко"),
        ("car","машина"),
        ("teacher","учитель"),
        ("city","город"),
        ("music","музыка"),
        ("phone","телефон"),
        ("river","река"),
        ("sun","солнце"),
        ("book","книга"),
        ("dog","собака")
    ]

    random.shuffle(words)

    alias_games[user_id] = {
        "words": words,
        "index": 0,
        "user_score": 0,
        "bot_score": 0,
        "attempts": 0,
        "phase": "bot"
    }

    return words


async def handle_user(bot, message, text):
    user_id = message.from_user.id
    game = alias_games[user_id]

    if game["phase"] == "bot":
        await user_guess(bot, message, text)
    else:
        await bot_guess(bot, message, text)


async def bot_explains(bot, user_id):
    game = alias_games[user_id]

    if game["index"] >= 10:
        await finish(bot, user_id)
        return

    word = game["words"][game["index"]][0]

    prompt = f'Explain the word "{word}" without saying it.'

    explanation = chat(prompt)
    voice = await tts(explanation)

    await bot.send_voice(user_id, voice)
    await bot.send_message(user_id, f"{game['index']+1}/10")


async def user_guess(bot, message, text):
    user_id = message.from_user.id
    game = alias_games[user_id]

    word = game["words"][game["index"]][0]

    if word.lower() in text.lower():
        game["user_score"] += 1
        game["index"] += 1
        game["attempts"] = 0

        await bot.send_message(user_id, "✅ Correct!")

        game["phase"] = "user"
        await ask_user(bot, user_id)

    else:
        game["attempts"] += 1

        if game["attempts"] >= 3:
            await bot.send_message(user_id, f"❌ It was: {word}")

            game["index"] += 1
            game["attempts"] = 0

            game["phase"] = "user"
            await ask_user(bot, user_id)
        else:
            await bot.send_message(user_id, "Try again")


async def ask_user(bot, user_id):
    game = alias_games[user_id]

    text = "Теперь твоя очередь!\n\nСлова:\n"

    for w, tr in game["words"]:
        text += f"{w} - {tr}\n"

    await bot.send_message(user_id, text)


async def bot_guess(bot, message, text):
    user_id = message.from_user.id
    game = alias_games[user_id]

    prompt = f'User describes a word: "{text}". Guess one word.'

    guess = chat(prompt)

    real_words = [w for w, _ in game["words"]]

    if guess.lower() in real_words:
        game["bot_score"] += 1
        await bot.send_message(user_id, f"🤖 {guess} ✅")
    else:
        await bot.send_message(user_id, f"🤖 {guess}")

    game["phase"] = "bot"
    await bot_explains(bot, user_id)


async def finish(bot, user_id):
    game = alias_games[user_id]

    result = f"""
Игра окончена

Ты: {game['user_score']}
Бот: {game['bot_score']}
"""

    await bot.send_message(user_id, result)

    del alias_games[user_id]