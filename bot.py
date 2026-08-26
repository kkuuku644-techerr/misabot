import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8965338371:AAG1ksD8FlTtaNMNcHljZENqNfijQuvT0BA"
RAID_CHANNEL_ID = -1004404647295      # ID рейд-канала (куда летят принятые тейки)
ADMIN_CHAT_ID = -1003941038109        # ID админ-чата (куда приходят тейки на модерацию)
MY_ADMIN_ID = 7959524856              # Твой личный Telegram ID (админ)
BOT_USERNAME = "misamsa_bot"         # Укажи юзернейм своего бота (без @) для кнопок в канале

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# База данных в памяти (для продакшна лучше подключить БД)
# Структура: { user_id: {"balance": int, "username": str} }
users_db = {}
# Временное хранилище тейков на модерацию: { message_id_в_админ_чате: {"user_id": int, "chat_id": int, "msg_id": int} }
pending_takes = {}

def get_user(user_id: int, username: str = "User"):
    if user_id not in users_db:
        users_db[user_id] = {"balance": 50, "username": username or "User"}  # Стартовый бонус 50 конфет
    return users_db[user_id]

# --- НИЖНЯЯ КЛАВИАТУРА ДЛЯ ЛИЧКИ ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📥 Слить")],
        [KeyboardButton(text="🎮 Игры")]
    ],
    resize_keyboard=True
)

# Функция проверки подписки на рейд-канал
async def check_user_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=RAID_CHANNEL_ID, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        return False
    except TelegramBadRequest:
        return True  # Заглушка на случай, если бот не админ в канале
    except Exception:
        return False

# --- СТАРТ И ГЛАВНОЕ МЕНЮ ---
@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message):
    get_user(message.from_user.id, message.from_user.username)
    text = (
        "✨ **Привет! Это официальный бот @misaraid**\n\n"
        "Тут ты можешь сливать тейки и играть в игры от Мисы 🖤\n\n"
        "Выбирай нужный раздел на клавиатуре снизу 👇"
    )
    await message.answer(text, reply_markup=main_keyboard, parse_mode=ParseMode.MARKDOWN)


# --- КНОПКИ ЛИЧКИ ---
@router.message(F.chat.type == "private", F.text == "👤 Профиль")
async def profile_handler(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    is_sub = await check_user_subscription(message.from_user.id)
    sub_status = "✅ Подписан(-а)" if is_sub else "❌ Не подписан(-а)"

    text = (
        f"👤 **Твой профиль:**\n\n"
        f"🆔 ID: `{message.from_user.id}`\n"
        f"📌 Имя: {message.from_user.first_name}\n"
        f"📢 Статус канала: {sub_status}\n"
        f"🍬 Баланс: **{user['balance']} конфет**"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.chat.type == "private", F.text == "📥 Слить")
async def take_info_handler(message: Message):
    await message.answer(
        "📥 **Отправь свой тейк следующим сообщением!**\n\n"
        "Это может быть текст, фото, видео или документ. Я отправлю его админам на проверку.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.chat.type == "private", F.text == "🎮 Игры")
async def games_menu_handler(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Кубик (Ставка: 10)", callback_data="game_dice"),
         InlineKeyboardButton(text="🎯 Дартс (Ставка: 10)", callback_data="game_darts")],
        [InlineKeyboardButton(text="🎰 Слоты (Ставка: 15)", callback_data="game_slot"),
         InlineKeyboardButton(text="💣 Мины (Ставка: 20)", callback_data="game_mines")],
        [InlineKeyboardButton(text="🎳 Боулинг (Ставка: 10)", callback_data="game_bowling"),
         InlineKeyboardButton(text="🏀 Баскетбол (Ставка: 10)", callback_data="game_basketball")],
    ])
    await message.answer("🎮 **Мини-игры от Мисы**\nВыбирай игру через кнопки или пиши в чате (например: `мины 20`, `слоты 15`, `кубик 10`):", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


# --- ОТПРАВКА ТЕЙКА НА МОДЕРАЦИЮ ---
@router.message(F.chat.type == "private", ~F.text.startswith('/'), ~F.text.in_({"👤 Профиль", "📥 Слить", "🎮 Игры"}))
async def handle_take_submission(message: Message):
    user_id = message.from_user.id

    # Проверка подписки
    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        sub_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{RAID_CHANNEL_ID}")],
            [InlineKeyboardButton(text="🔄 Я подписался (-ась)", callback_data="check_sub")]
        ])
        await message.answer(
            "❌ **Тейк не принят!**\n\nЧтобы сливать материалы, подпишись на наш канал, а затем нажми кнопку ниже 👇",
            reply_markup=sub_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Пересылаем тейк в админский чат
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"take_accept_{user_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"take_reject_{user_id}")]
    ])

    try:
        forwarded = await message.send_copy(chat_id=ADMIN_CHAT_ID, reply_markup=admin_kb)
        pending_takes[forwarded.message_id] = {
            "user_id": user_id,
            "chat_id": message.chat.id,
            "msg_id": message.message_id
        }
        await message.answer("📤 **Тейк отправлен на модерацию админам!** Жди публикации.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logging.error(f"Error forwarding take: {e}")
        await message.answer("⚠️ Ошибка при отправке тейка.")

@router.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery):
    is_subscribed = await check_user_subscription(callback.from_user.id)
    if is_subscribed:
        await callback.message.edit_text("✅ **Подписка подтверждена!** Отправь свой тейк сообщением заново.", parse_mode=ParseMode.MARKDOWN)
    else:
        await callback.answer("❌ Ты всё еще не подписан(-а) на канал!", show_alert=True)


# --- МОДЕРАЦИЯ ТЕЙКОВ В АДМИН-ЧАТЕ ---
@router.callback_query(F.data.startswith("take_"))
async def process_moderation(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    action = data_parts[1] # accept или reject
    target_user_id = int(data_parts[2])
    msg_id = callback.message.message_id

    if msg_id not in pending_takes:
        await callback.answer("⚠️ Этот тейк уже обработан или устарел.", show_alert=True)
        return

    take_info = pending_takes[msg_id]

    if action == "accept":
        try:
            # Публикуем в рейд-канал с цитированием от Мисабота
            channel_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Мисабот || 🖤", url=f"https://t.me/{BOT_USERNAME}")]
            ])

            sent_msg = await bot.copy_message(
                chat_id=RAID_CHANNEL_ID,
                from_chat_id=take_info["chat_id"],
                message_id=take_info["msg_id"],
                reply_markup=channel_kb
            )

            if sent_msg:
                # Начисляем конфетки автору
                user = get_user(target_user_id)
                user["balance"] += 10

                # Уведомляем автора
                await bot.send_message(
                    target_user_id,
                    "🎉 **Ваш тейк успешно был принят в канал!**\n🎁 Вам начислено: **+10 🍬**",
                    parse_mode=ParseMode.MARKDOWN
                )

                await callback.message.edit_text(f"{callback.message.text}\n\n✅ **ПРИНЯТО** администратором @{callback.from_user.username or 'admin'}")
                del pending_takes[msg_id]
        except Exception as e:
            logging.error(f"Publish error: {e}")
            await callback.answer(f"❌ Ошибка публикации: {e}", show_alert=True)

    elif action == "reject":
        try:
            await bot.send_message(
                target_user_id,
                "❌ **К сожалению, ваш тейк был отклонен администрацией.**",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.message.edit_text(f"{callback.message.text}\n\n❌ **ОТКЛОНЕНО** администратором @{callback.from_user.username or 'admin'}")
            del pending_takes[msg_id]
        except Exception:
            pass

    await callback.answer()


# --- ИГРЫ И КОМАНДЫ (РАБОТАЮТ И В ЛИЧКЕ, И В ГРУППАХ) ---

async def play_game(message: Message, game_type: str, bet: int):
    user = get_user(message.from_user.id, message.from_user.username)

    if user["balance"] < bet:
        await message.answer(f"❌ @{message.from_user.username or 'Игрок'}, у тебя недостаточно конфет! Твой баланс: {user['balance']} 🍬")
        return

    user["balance"] -= bet

    if game_type == "dice":
        msg = await message.answer_dice(emoji="🎲")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 4:
            win = bet * 2
            user["balance"] += win
            await message.answer(f"🎉 Выпало {val}! Ты выиграл **{win} 🍬**!")
        else:
            await message.answer(f"😢 Выпало {val}. Ставка сгорела.")

    elif game_type == "darts":
        msg = await message.answer_dice(emoji="🎯")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 4:
            win = bet * 3
            user["balance"] += win
            await message.answer(f"🎯 В яблочко! Выигрыш: **{win} 🍬**!")
        else:
            await message.answer("❌ Мимо центра!")

    elif game_type == "slot":
        msg = await message.answer_dice(emoji="🎰")
        await asyncio.sleep(3)
        val = msg.dice.value
        if val in [1, 22, 43, 64]:
            win = bet * 5
            user["balance"] += win
            await message.answer(f"🎰 ДЖЕКПОТ! Выигрыш: **{win} 🍬**!")
        else:
            await message.answer("❌ Казино забирает твои конфеты.")

    elif game_type == "mines":
        # Упрощенная механика мин: 50/50 шанс умножить на х2.2 или сгореть
        await message.answer("💣 Ищем безопасные пути на минном поле...")
        await asyncio.sleep(2)
        if random.random() > 0.45: # 55% победа
            win = int(bet * 2.2)
            user["balance"] += win
            await message.answer(f"💥 Успешно! Поле разминировано. Выигрыш: **{win} 🍬**!")
        else:
            await message.answer("💥 Бабах! Ты подорвался на мине, ставка сгорела.")

    elif game_type == "bowling":
        msg = await message.answer_dice(emoji="🎳")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 5:
            win = bet * 3
            user["balance"] += win
            await message.answer(f"🎳 Страйк! Выигрыш: **{win} 🍬**!")
        else:
            await message.answer("❌ Кегли устояли.")

    elif game_type == "basketball":
        msg = await message.answer_dice(emoji="🏀")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 4:
            win = bet * 2
            user["balance"] += win
            await message.answer(f"🏀 Гол в кольцо! Выигрыш: **{win} 🍬**!")
        else:
            await message.answer("❌ Мимо кольца.")


# Обработка игр через инлайн-кнопки в личке
@router.callback_query(F.data.startswith("game_"))
async def process_inline_games(callback: CallbackQuery):
    action = callback.data.split("_")[1]
    bets = {"dice": 10, "darts": 10, "slot": 15, "mines": 20, "bowling": 10, "basketball": 10}
    bet = bets.get(action, 10)

    # Создаем фейковое сообщение для вызова игровой логики
    await play_game(callback.message, action, bet)
    await callback.answer()


# Команды для чатов и лички (например: мины 50, слоты 20, баланс, профиль)
@router.message(F.text.lower().startswith(("баланс", "профиль")))
async def cmd_profile_text(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"👤 **Профиль игрока:**\n"
        f"🆔 ID в ТГ: `{message.from_user.id}`\n"
        f"📌 Имя: {message.from_user.first_name}\n"
        f"🍬 Баланс: **{user['balance']} конфет**",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.text.lower().startswith("мины"))
async def cmd_mines(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
    await play_game(message, "mines", bet)

@router.message(F.text.lower().startswith("слоты"))
async def cmd_slots(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 15
    await play_game(message, "slot", bet)

@router.message(F.text.lower().startswith("кубик"))
async def cmd_dice(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    await play_game(message, "dice", bet)

@router.message(F.text.lower().startswith("дартс"))
async def cmd_darts(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    await play_game(message, "darts", bet)


# --- АДМИН-ПАНЕЛЬ (ТОЛЬКО ДЛЯ ТЕБЯ) ---
@router.message(Command("admin"), F.chat.type == "private")
async def cmd_admin(message: Message):
    if message.from_user.id != MY_ADMIN_ID:
        return

    text = (
        "👑 **Админ-панель Мисабота**\n\n"
        "Команды управления:\n"
        "• `/give ID СУММА` — выдать конфеты\n"
        "• `/take ID СУММА` — забрать конфеты\n"
        "• `/stats` — статистика базы"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("give"), F.chat.type == "private")
async def cmd_give(message: Message):
    if message.from_user.id != MY_ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit() or not args[2].isdigit():
        await message.answer("⚠️ Формат: `/give ID сумма`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = int(args[1])
    amount = int(args[2])
    user = get_user(target_id)
    user["balance"] += amount
    await message.answer(f"✅ Успешно выдано {amount} 🍬 игроку с ID `{target_id}`.", parse_mode=ParseMode.MARKDOWN)

@router.message(Command("take"), F.chat.type == "private")
async def cmd_take(message: Message):
    if message.from_user.id != MY_ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit() or not args[2].isdigit():
        await message.answer("⚠️ Формат: `/take ID сумма`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = int(args[1])
    amount = int(args[2])
    user = get_user(target_id)
    user["balance"] = max(0, user["balance"] - amount)
    await message.answer(f"✅ Успешно списано {amount} 🍬 у игрока с ID `{target_id}`.", parse_mode=ParseMode.MARKDOWN)

@router.message(Command("stats"), F.chat.type == "private")
async def cmd_stats(message: Message):
    if message.from_user.id != MY_ADMIN_ID:
        return
    total_users = len(users_db)
    total_candies = sum(u["balance"] for u in users_db.values())
    await message.answer(f"📊 Статистика:\n👥 Игроков в базе: `{total_users}`\n🍬 Конфет на руках: `{total_candies}`", parse_mode=ParseMode.MARKDOWN)


# --- ЗАПУСК БОТА ---
async def main():
    print("Мисабот запущен и готов к работе!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())

