from data.users import speaking, stats
from services.voice import tts
from services.openai import chat
import time

async def start(message):
    user_id = message.from_user.id

    speaking[user_id] = {"stage": "name"}
    stats[user_id] = {"time": 0, "start": time.time()}

    v = await tts("Hello! What is your name?")
    await message.answer_voice(v)


async def handle(bot, message, text):
    user_id = message.from_user.id
    s = speaking[user_id]

    if s["stage"] == "name":
        s["name"] = text
        s["stage"] = "topic"

        v = await tts("Choose topic: travel, food, life or say your own")
        await bot.send_voice(user_id, v)
        return

    if s["stage"] == "topic":
        s["topic"] = text
        s["stage"] = "chat"

        v = await tts(f"Great {s['name']}! Let's talk about {text}")
        await bot.send_voice(user_id, v)
        return

    prompt = f"""
You are friendly English tutor.

User: {text}

1. Correct mistakes
2. Explain short
3. Continue dialog
4. Ask question
"""

    reply = chat(prompt)
    v = await tts(reply)

    await bot.send_voice(user_id, v)