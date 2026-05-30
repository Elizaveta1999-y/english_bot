@router.message(F.text)
async def text_in_roleplay(message: Message):
    print(f"[DEBUG] roleplay.py got text: {message.text}")  # <-- добавить
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    print(f"[DEBUG] roleplay awaiting_custom_scenario: {user_state.get('awaiting_custom_scenario')}")  # <-- добавить
    ...