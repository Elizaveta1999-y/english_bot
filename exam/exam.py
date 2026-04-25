from services.deepseek import chat

exam = {}

def start(user_id):
    exam[user_id] = {
        "score": 0,
        "step": 0
    }

def generate():
    return chat(""" 
Create English exam like OGE/EGE: one question with 3 answer choices (A, B, C). 
Provide the correct answer at the end. Keep it short.
""", max_tokens=200)

async def send_task(message):
    user_id = message.from_user.id
    task = generate()
    exam[user_id]["task"] = task
    await message.answer(task)

async def check(message):
    user_id = message.from_user.id
    exam[user_id]["score"] += 1
    await message.answer("Ответ принят")
    await send_task(message)