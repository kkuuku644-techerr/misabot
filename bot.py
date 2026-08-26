import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

TOKEN = "8965338371:AAG1ksD8FlTtaNMNcHljZENqNfijQuvT0BA"
RAID_CHANNEL_ID = -1004404647295
ADMIN_CHAT_ID = -1003941038109
MY_ADMIN_ID = 7959524856
BOT_USERNAME = "ТУТ_ЮЗЕРНЕЙМ_БОТА"  # Замени на юзернейм своего бота без @

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

users_db = {}
pending_takes = {}

def get_user(user_id: int, username: str = "User"):
    uid = str(user_id)
    if uid not in users_db:
        users_db[uid] = {"balance": 50, "username": username or "User"}
    return users_db[uid]

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Профиль"), KeyboardButton(text="Слить")],
        [KeyboardButton(text="Игры")]
    ],
    resize_keyboard=True
)

async def check_user_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=RAID_CHANNEL_ID, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        return False
    except TelegramBadRequest:
        return True
    except Exception:
        return False

@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message):
    get_user(message.from_user.id, message.from_user.username)
    text = (
        "Привет. Это официальный бот.\n\n"
        "Здесь ты можешь отправлять тейки и играть в игры.\n\n"
        "Выбирай нужный раздел на клавиатуре снизу."
    )
    await message.answer(text, reply_markup=main_keyboard, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "Профиль")
async def profile_handler(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    is_sub = await check_user_subscription(message.from_user.id)
    sub_status = "Подписан" if is_sub else "Не подписан"

    text = (
        f"Твой профиль:\n\n"
        f"ID: `{message.from_user.id}`\n"
        f"Имя: {message.from_user.first_name}\n"
        f"Статус канала: {sub_status}\n"
        f"Баланс: **{user['balance']} конфет**"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "Слить")
async def take_info_handler(message: Message):
    if message.chat.type != "private":
        await message.answer("Сливать тейки можно только в личном чате с ботом.")
        return
    await message.answer(
        "Отправь свой тейк следующим сообщением.\n\n"
        "Это может быть текст, фото, видео или документ. Он будет отправлен админам на проверку.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.text == "Игры")
async def games_menu_handler(message: Message):
    if message.chat.type != "private":
        await message.answer("Играть через меню можно только в личном чате с ботом. В группах используй команды: мины <ставка>, слоты <ставка>, кубик <ставка>, дартс <ставка>.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кубик (Ставка: 10)", callback_data="game_dice"),
         InlineKeyboardButton(text="Дартс (Ставка: 10)", callback_data="game_darts")],
        [InlineKeyboardButton(text="Слоты (Ставка: 15)", callback_data="game_slot"),
         InlineKeyboardButton(text="Мины (Ставка: 20)", callback_data="game_mines")],
        [InlineKeyboardButton(text="Боулинг (Ставка: 10)", callback_data="game_bowling"),
         InlineKeyboardButton(text="Баскетбол (Ставка: 10)", callback_data="game_basketball")],
    ])
    await message.answer("Мини-игры\nВыбирай игру через кнопки или пиши в чате (например: мины 20, слоты 15, кубик 10):", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@router.message(F.chat.type == "private", ~F.text.startswith('/'), ~F.text.in_({"Профиль", "Слить", "Игры"}))
async def handle_take_submission(message: Message):
    user_id = message.from_user.id
    get_user(user_id, message.from_user.username)

    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        sub_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал", url=f"https://t.me/c/{str(RAID_CHANNEL_ID)[4:]}/1")],
            [InlineKeyboardButton(text="Я подписался", callback_data="check_sub")]
        ])
        await message.answer(
            "Тейк не принят.\n\nЧтобы отправлять материалы, подпишись на канал, а затем нажми кнопку ниже.",
            reply_markup=sub_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Принять", callback_data=f"take_accept_{user_id}"),
         InlineKeyboardButton(text="Отклонить", callback_data=f"take_reject_{user_id}")]
    ])

    try:
        forwarded = await message.send_copy(chat_id=ADMIN_CHAT_ID, reply_markup=admin_kb)
        pending_takes[forwarded.message_id] = {
            "user_id": user_id,
            "chat_id": message.chat.id,
            "msg_id": message.message_id
        }
        await message.answer("Тейк отправлен на модерацию админам.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logging.error(f"Error forwarding take: {e}")
        await message.answer("Ошибка при отправке тейка.")

@router.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery):
    is_subscribed = await check_user_subscription(callback.from_user.id)
    if is_subscribed:
        await callback.message.edit_text("Подписка подтверждена. Отправь свой тейк сообщением заново.", parse_mode=ParseMode.MARKDOWN)
    else:
        await callback.answer("Ты еще не подписан на канал.", show_alert=True)

@router.callback_query(F.data.startswith("take_"))
async def process_moderation(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    action = data_parts[1]
    target_user_id = int(data_parts[2])
    msg_id = callback.message.message_id

    if msg_id not in pending_takes:
        await callback.answer("Этот тейк уже обработан или устарел.", show_alert=True)
        return

    take_info = pending_takes[msg_id]

    if action == "accept":
        try:
            header = f"<a href='https://t.me/{BOT_USERNAME}'>Мисабот</a> ||\n\n"
            original_chat_id = take_info["chat_id"]
            original_msg_id = take_info["msg_id"]

            try:
                orig_msg = await bot.get_message(chat_id=original_chat_id, message_id=original_msg_id)
                text_to_send = orig_msg.text or orig_msg.caption or ""
            except Exception:
                text_to_send = ""

            if text_to_send:
                if orig_msg.text:
                    await bot.send_message(
                        chat_id=RAID_CHANNEL_ID,
                        text=header + text_to_send,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                elif orig_msg.photo:
                    photo_id = orig_msg.photo[-1].file_id
                    await bot.send_photo(
                        chat_id=RAID_CHANNEL_ID,
                        photo=photo_id,
                        caption=header + text_to_send,
                        parse_mode="HTML"
                    )
                elif orig_msg.video:
                    video_id = orig_msg.video.file_id
                    await bot.send_video(
                        chat_id=RAID_CHANNEL_ID,
                        video=video_id,
                        caption=header + text_to_send,
                        parse_mode="HTML"
                    )
            else:
                await bot.copy_message(
                    chat_id=RAID_CHANNEL_ID,
                    from_chat_id=original_chat_id,
                    message_id=original_msg_id
                )

            user = get_user(target_user_id)
            user["balance"] += 10

            await bot.send_message(
                target_user_id,
                "Ваш тейк успешно был принят в канал.\nНачислено: +10 конфет",
                parse_mode=ParseMode.MARKDOWN
            )

            await callback.message.edit_text(f"{callback.message.text}\n\nПРИНЯТО администратором @{callback.from_user.username or 'admin'}")
            del pending_takes[msg_id]
        except Exception as e:
            logging.error(f"Publish error: {e}")
            await callback.answer(f"Ошибка публикации: {e}", show_alert=True)

    elif action == "reject":
        try:
            await bot.send_message(
                target_user_id,
                "К сожалению, ваш тейк был отклонен администрацией.",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.message.edit_text(f"{callback.message.text}\n\nОТКЛОНЕНО администратором @{callback.from_user.username or 'admin'}")
            del pending_takes[msg_id]
        except Exception:
            pass

    await callback.answer()

async def play_game(user_id: int, username: str, message: Message, game_type: str, bet: int):
    user = get_user(user_id, username)

    if user["balance"] < bet:
        await message.answer(f"У тебя недостаточно конфет. Твой баланс: {user['balance']} конфет")
        return

    user["balance"] -= bet

    if game_type == "dice":
        msg = await message.answer_dice(emoji="🎲")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 4:
            win = bet * 2
            user["balance"] += win
            await message.answer(f"Выпало {val}. Выигрыш: {win} конфет. Баланс: {user['balance']} конфет")
        else:
            await message.answer(f"Выпало {val}. Ставка сгорела. Баланс: {user['balance']} конфет")

    elif game_type == "darts":
        msg = await message.answer_dice(emoji="🎯")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 4:
            win = bet * 3
            user["balance"] += win
            await message.answer(f"В яблочко. Выигрыш: {win} конфет. Баланс: {user['balance']} конфет")
        else:
            await message.answer(f"Мимо центра. Баланс: {user['balance']} конфет")

    elif game_type == "slot":
        msg = await message.answer_dice(emoji="🎰")
        await asyncio.sleep(3)
        val = msg.dice.value
        if val in [1, 22, 43, 64]:
            win = bet * 5
            user["balance"] += win
            await message.answer(f"Джекпот. Выигрыш: {win} конфет. Баланс: {user['balance']} конфет")
        else:
            await message.answer(f"Ставка сгорела. Баланс: {user['balance']} конфет")

    elif game_type == "mines":
        await message.answer("Ищем безопасные пути на минном поле...")
        await asyncio.sleep(2)
        if random.random() > 0.45:
            win = int(bet * 2.2)
            user["balance"] += win
            await message.answer(f"Успешно. Выигрыш: {win} конфет. Баланс: {user['balance']} конфет")
        else:
            await message.answer(f"Подорвался на мине. Баланс: {user['balance']} конфет")

    elif game_type == "bowling":
        msg = await message.answer_dice(emoji="🎳")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 5:
            win = bet * 3
            user["balance"] += win
            await message.answer(f"Страйк. Выигрыш: {win} конфет. Баланс: {user['balance']} конфет")
        else:
            await message.answer(f"Кегли устояли. Баланс: {user['balance']} конфет")

    elif game_type == "basketball":
        msg = await message.answer_dice(emoji="🏀")
        await asyncio.sleep(4)
        val = msg.dice.value
        if val >= 4:
            win = bet * 2
            user["balance"] += win
            await message.answer(f"Гол в кольцо. Выигрыш: {win} конфет. Баланс: {user['balance']} конфет")
        else:
            await message.answer(f"Мимо кольца. Баланс: {user['balance']} конфет")

@router.callback_query(F.data.startswith("game_"))
async def process_inline_games(callback: CallbackQuery):
    action = callback.data.split("_")[1]
    bets = {"dice": 10, "darts": 10, "slot": 15, "mines": 20, "bowling": 10, "basketball": 10}
    bet = bets.get(action, 10)

    await play_game(callback.from_user.id, callback.from_user.username, callback.message, action, bet)
    await callback.answer()

@router.message(F.text.lower().in_({"баланс", "профиль"}))
async def cmd_profile_text(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Профиль игрока:\n"
        f"ID в ТГ: `{message.from_user.id}`\n"
        f"Имя: {message.from_user.first_name}\n"
        f"Баланс: **{user['balance']} конфет**",
        parse_mode=ParseMode.MARKDOWN
    )

# --- ПЕРЕДАЧА КОНФЕТ ---
@router.message(F.text.lower().startswith("передать"))
async def cmd_transfer(message: Message):
    sender_id = message.from_user.id
    sender = get_user(sender_id, message.from_user.username)
    args = message.text.split()

    target_id = None
    amount = 0

    # Вариант 1: ответом на сообщение (например, "передать 50")
    if message.reply_to_message and len(args) == 2 and args[1].isdigit():
        target_id = message.reply_to_message.from_user.id
        amount = int(args[1])
        target_username = message.reply_to_message.from_user.first_name

    # Вариант 2: по ID (например, "передать 123456789 50")
    elif len(args) == 3 and args[1].isdigit() and args[2].isdigit():
        target_id = int(args[1])
        amount = int(args[2])
        target_username = f"ID {target_id}"

    if not target_id or amount <= 0:
        await message.answer("Формат передачи:\n1) Ответом на сообщение: `передать <сумма>`\n2) По ID: `передать <ID> <сумма>`", parse_mode=ParseMode.MARKDOWN)
        return

    if sender_id == target_id:
        await message.answer("Нельзя передавать конфеты самому себе.")
        return

    if sender["balance"] < amount:
        await message.answer(f"У тебя недостаточно конфет. Твой баланс: {sender['balance']} конфет")
        return

    # Выполняем перевод
    sender["balance"] -= amount
    target = get_user(target_id)
    target["balance"] += amount

    await message.answer(f"Успешно передано {amount} конфет игроку {target_username}. Твой баланс: {sender['balance']} конфет")

@router.message(F.text.lower().startswith("мины"))
async def cmd_mines(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
    await play_game(message.from_user.id, message.from_user.username, message, "mines", bet)

@router.message(F.text.lower().startswith("слоты"))
async def cmd_slots(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 15
    await play_game(message.from_user.id, message.from_user.username, message, "slot", bet)

@router.message(F.text.lower().startswith("кубик"))
async def cmd_dice(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    await play_game(message.from_user.id, message.from_user.username, message, "dice", bet)

@router.message(F.text.lower().startswith("дартс"))
async def cmd_darts(message: Message):
    args = message.text.split()
    bet = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    await play_game(message.from_user.id, message.from_user.username, message, "darts", bet)

@router.message(Command("admin"), F.chat.type == "private")
async def cmd_admin(message: Message):
    if message.from_user.id != MY_ADMIN_ID:
        return

    text = (
        "Админ-панель\n\n"
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
        await message.answer("Формат: `/give ID сумма`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = int(args[1])
    amount = int(args[2])
    user = get_user(target_id)
    user["balance"] += amount
    await message.answer(f"Успешно выдано {amount} конфет игроку с ID `{target_id}`.", parse_mode=ParseMode.MARKDOWN)

@router.message(Command("take"), F.chat.type == "private")
async def cmd_take(message: Message):
    if message.from_user.id != MY_ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit() or not args[2].isdigit():
        await message.answer("Формат: `/take ID сумма`", parse_mode=ParseMode.MARKDOWN)
        return

    target_id = int(args[1])
    amount = int(args[2])
    user = get_user(target_id)
    user["balance"] = max(0, user["balance"] - amount)
    await message.answer(f"Успешно списано {amount} конфет у игрока с ID `{target_id}`.", parse_mode=ParseMode.MARKDOWN)

@router.message(Command("stats"), F.chat.type == "private")
async def cmd_stats(message: Message):
    if message.from_user.id != MY_ADMIN_ID:
        return
    total_users = len(users_db)
    total_candies = sum(u["balance"] for u in users_db.values())
    await message.answer(f"Статистика:\nИгроков в базе: `{total_users}`\nКонфет на руках: `{total_candies}`", parse_mode=ParseMode.MARKDOWN)

async def main():
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())

