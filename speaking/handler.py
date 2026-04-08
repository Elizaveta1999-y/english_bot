from data.users import speaking
from services.voice import tts
from services.openai import chat


async def start(message):
    user_id = message.from_user.id

    speaking[user_id] = {
        "stage": "start"
    }

    v = await tts("Hello! Let's practice speaking. Tell me something about your day.")
    await message.answer_voice(v)


async def handle(bot, message, text):
    user_id = message.from_user.id

    prompt = f"""
You are a friendly English tutor.

User said: {text}

1. Correct mistakes
2. Explain shortly
3. Continue conversation
4. Ask question

Speak simple English.
"""

    reply = chat(prompt)

    v = await tts(reply)
    await bot.send_voice(user_id, v)