# Этап 1: ожидание имени
if user_state.get("waiting_for_name"):
    # Очищаем от мусора, оставляем только возможное имя (первые 20 символов)
    raw_name = user_text.strip()
    # Если распознавание дало длинную фразу, возьмём первое слово
    name = raw_name.split()[0][:20]
    set_user_name(user_id, name)
    user_state["waiting_for_name"] = False
    set_user_mode(user_id, "speaking_active")
    set_user_state(user_id, user_state)

    voice_msg = f"Nice to meet you, {name}! Let's practice English. Just speak naturally. I'll correct your mistakes. Go ahead, say something!"
    voice_file = await text_to_voice(voice_msg)
    if voice_file:
        await message.answer_voice(voice_file)
    return