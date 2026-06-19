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
            "\U0001F4B3 <b>Ваша подписка активна</b>\n\n"
            f"\U0001F4C5 Дата окончания: {expires}\n"
            "\U0001F4B0 Тариф: 900 ₽/мес\n\n"
            "Чтобы продлить, нажмите кнопку ниже."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001F504 Продлить подписку", callback_data="profile_extend")],
            [InlineKeyboardButton(text="\U0001F519 Назад", callback_data="back_to_main")]
        ])
    else:
        text = (
            "\U0001F48E <b>Premium подписка</b>\n\n"
            "Откройте все возможности AI English US для изучения английского без ограничений.\n\n"
            "<b>Что входит в подписку:</b>\n\n"
            "\U0001F4DA <b>Все уроки</b> — от A1 до C2, включая тематические. Теория и практика по каждой теме.\n"
            "\U0001F4DD <b>Language Skills</b> — тренируйте чтение, письмо, аудирование и говорение. Задания по формату ОГЭ/ЕГЭ с проверкой ИИ.\n"
            "\U0001F5C2️ <b>Словарь с интервальным повторением</b> — учите слова эффективно, забывайте реже.\n"
            "\U0001F3A4 <b>Режим Speaking</b> — свободный диалог с ИИ-тьютором с коррекцией ошибок.\n"
            "\U0001F3AD <b>RolePlay</b> — практика языка в ролевых играх на разные темы.\n"
            "\U0001F4CA <b>Персональная статистика</b> — отслеживайте прогресс: уроки, практики, точность ответов, дни подряд.\n\n"
            "<b>Почему это выгоднее репетитора:</b>\n\n"
            "• Занятия с репетитором стоят от 1500 ₽ за час.\n"
            "• Premium даёт вам неограниченную практику 24/7 за 900 ₽ в месяц.\n"
            "• Вы занимаетесь в любое время без записи и привязки к расписанию.\n"
            "• ИИ-тьютор всегда на связи — отвечает мгновенно и терпеливо объясняет ошибки.\n"
            "• За месяц вы получаете десятки часов практики по цене одного занятия с репетитором.\n\n"
            "<b>Цена:</b> 900 ₽ / месяц\n\n"
            "Оплатите подписку и занимайтесь английским в любое время, в удобном для вас темпе."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001F4B3 Оплатить подписку", callback_data="profile_extend")],
            [InlineKeyboardButton(text="\U0001F519 Назад", callback_data="back_to_main")]
        ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")