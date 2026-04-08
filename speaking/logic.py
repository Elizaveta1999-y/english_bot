from services.openai import chat

def reply(user_text, name, topic):
    prompt = f"""
You are a friendly English teacher.

Student: {name}
Topic: {topic}

User: {user_text}

1. Correct mistakes
2. Explain shortly
3. Continue conversation
4. Ask question

Speak simple and friendly.
"""
    return chat(prompt)