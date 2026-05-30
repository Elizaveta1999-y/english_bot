@router.message(F.text)
async def text_in_speaking(message: Message):
    print(f"[DEBUG] speaking.py got text: {message.text}")  # <-- добавить
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    mode = user_state.get("mode")
    print(f"[DEBUG] speaking mode: {mode}")  # <-- добавить
    ...