from services.openai import chat

exam = {}

def start(user_id):
    exam[user_id] = {
        "score": 0,
        "step": 0
    }


def generate():
    return chat("""
Create English exam like OGE/EGE:
Question + A B C + correct answer
""")


async def send_task(message):
    user_id = message.from_user.id

    task = generate()
    exam[user_id]["task"] = task

    await message.answer(task)


async def check(message):
    user_id = message.from_user.id
    exam[user_id]["score"] += 1

    await message.answer("Ответ принят ✅")
    await send_task(message)