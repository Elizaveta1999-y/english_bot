# handlers/subscription.py
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from data.users import get_user_state

router = Router()

@router.message(F.text == "/subscription")
async def show_subscription(message: Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    sub = state.get("profile", {}).get("subscription", {})
    
    if sub.get("active"):
        expires = sub.get("expires", "не указана")
        text = (
            f"<b>Ваша подписка активна</b>\n\n"
            f"📅 Дата окончания: {expires}\n"
            f"Тариф: 900 ₽/мес\n\n"
            f"Чтобы продлить, нажмите кнопку ниже."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="profile_extend")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    else:
        text = (
⭐ <b>Premium подписка</b>

Откройте все возможности AI English US для изучения английского без ограничений.

<b>Что входит в подписку:</b>

📚 <b>Все уроки</b> — от A1 до C2, включая тематические. Теория и практика по каждой теме.
📝 <b>Language Skills</b> — тренируйте чтение, письмо, аудирование и говорение. Задания по формату ОГЭ/ЕГЭ с проверкой ИИ.
🗂️ <b>Словарь с интервальным повторением</b> — учите слова эффективно, забывайте реже.
🎤 <b>Режим Speaking</b> — свободный диалог с ИИ-тьютором с коррекцией ошибок.
🎭 <b>RolePlay</b> — практика языка в ролевых играх на разные темы.
📊 <b>Персональная статистика</b> — отслеживайте прогресс: уроки, практики, точность ответов, дни подряд.

<b>Почему это выгоднее репетитора:</b>

• Занятия с репетитором стоят от 1500 ₽ за час.
• Premium даёт вам неограниченную практику 24/7 за 900 ₽ в месяц.
• Вы занимаетесь в любое время без записи и привязки к расписанию.
• ИИ-тьютор всегда на связи — отвечает мгновенно и терпеливо объясняет ошибки.
• За месяц вы получаете десятки часов практики по цене одного занятия с репетитором.

<b>Цена:</b> 900 ₽ / месяц

Оплатите подписку и занимайтесь английским в любое время, в удобном для вас темпе.

[💳 Оплатить подписку]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить подписку", callback_data="profile_extend")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")