async def process_voice_message(user_id: int, user_text: str) -> str:
    # Просто возвращаем эхо, чтобы проверить цепочку
    return f"You said: {user_text}"