import telebot
from telethon import TelegramClient
import requests
from time import sleep
from datetime import date, timedelta, datetime
from users import UserService
from threading import Thread

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open("assets/token.txt", "r") as f:
    TOKEN = f.readline().strip()

with open("assets/credentials.txt", "r") as f:
    api_id_bot = int(f.readline())
    api_hash_bot = f.readline().strip()

bot = telebot.TeleBot(TOKEN)
client_bot = TelegramClient(
    "bot", api_id_bot, api_hash_bot, system_version="4.16.30-vxCUSTOM"
).start(bot_token=TOKEN)
bot_loop = client_bot.loop

command_list_help = [
    "/start - Начать работу",
    "/help - Вывести список команд",
    "/setTime hh:mm - Установить время отправки дайджеста (в формате час:минута)",
    "/setPeriod n - Установить частоту отправки дайджеста (n в днях)",
    "/setLimit n - Установить размер дайджеста (где n - число новостей)",
    "/digest - Получить дайджест",
    "/settings - Вывести команды для пользовательских настроек",
    "/exit - Завершить работу",
]

command_list_settings = [
    "/add <id канала> - Подключить канал к дайджесту",
    "/del <id канала> - Отключить канал от дайджеста",
    "/getlist - Получить список подключенных каналов",
    "/getGroups - Получить список групп каналов",
    "/addChannelGroup <название группы каналов> - Создать группу каналов",
    "/addFeed <feed> - Добавить RSS/Atom-фид",
    "/delFeed <feed> - Удалить RSS/Atom-фид",
]

users = bot_loop.run_until_complete(UserService().init("127.0.0.1", 5000))

# Глобальный словарь: user_id -> команда, по которой ждём аргумент
pending_commands = {}

@bot.message_handler(commands=["start"])
def start_bot(message):
    user_id = message.from_user.id
    if bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    bot_loop.run_until_complete(users.register_user(login=user_id, name=str(user_id)))

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/help", "/digest")
    markup.row("/settings", "/exit")

    welcome_text = (
        "👋 Привет! Я ваш личный бот для получения дайджеста каналов.\n\n"
        "📋 Напишите /help, чтобы увидеть список доступных команд."
    )

    bot.send_message(
        message.from_user.id, welcome_text, reply_markup=markup, parse_mode="Markdown"
    )


@bot.message_handler(commands=["help"])
def help_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return
    help_text = "*Список доступных команд:*\n\n" + "\n".join(command_list_help)

    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("⚙️ Настройки", callback_data="open_settings")
    )

    bot.send_message(user_id, help_text, reply_markup=markup, parse_mode="Markdown")


def send_reaction_buttons(user_id, entity_id):
    metadata = f"{user_id},{entity_id}"
    markup = telebot.types.InlineKeyboardMarkup()
    btn_yes = telebot.types.InlineKeyboardButton("👍", callback_data=f"like_{metadata}")
    btn_no = telebot.types.InlineKeyboardButton("👎", callback_data=f"dislike_{metadata}")
    markup.add(btn_yes, btn_no)

    bot.send_message(user_id, "Понравилось? Оцените ниже:", reply_markup=markup)


async def forward_messages(user_id, messages):
    for m in messages:
        bot.send_message(user_id, m["description"] + "\n" + m["link"])
        send_reaction_buttons(user_id, m["entity_id"])


def make_data(user: str, limit: int, offset_date: datetime, channel_ids):
    return {
        "user": user,
        "limit": limit,
        "offset_date": str(offset_date),
        "channels": [{"name": id} for id in channel_ids],
    }


groups = {
    "По умолчанию": [],
}


@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    headers = {"Content-type": "application/json"}

    if call.data.startswith("like"):
        buffer = call.data[5:].split(",")
        data = {"user": buffer[0], "entity_id": int(buffer[1])}
        requests.post("http://127.0.0.1:8000/dislike", headers=headers, json=data)
        bot.answer_callback_query(call.id, "Спасибо за вашу оценку! 👍")

    elif call.data.startswith("dislike"):
        buffer = call.data[8:].split(",")
        data = {"user": buffer[0], "entity_id": int(buffer[1])}
        requests.post("http://127.0.0.1:8000/dislike", headers=headers, json=data)
        bot.answer_callback_query(call.id, "Учтём ваши замечания! 🙁")


    elif call.data.startswith("add$"):

        _, item_id, group_name = call.data.split("$")

        logger.info(f"Пользователь нажал кнопку: item_id={item_id}, group_name={group_name}")

        if group_name not in groups:
            groups[group_name] = []

        groups[group_name].append(item_id)

        logger.info(f"groups теперь: {groups}")

        bot.answer_callback_query(call.id, "Канал/фид успешно добавлен! ✅")


    elif call.data.startswith("digest"):
        _, group_name, user_id = call.data.split("$")
        bot.answer_callback_query(call.id, "Дайджест генерируется... ⏳")
        send_digest(
            int(user_id),
            date.today()
            - timedelta(
                days=bot_loop.run_until_complete(users.get_period(int(user_id))) or 1
            ),
            True,
        )

    elif call.data == "open_settings":
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("/add", "/del")
        markup.row("/addFeed", "/delFeed")
        markup.row("/getlist", "/getGroups")
        markup.row("/addChannelGroup", "/back_to_main")
        bot.send_message(call.message.chat.id, "⚙️ Настройки:", reply_markup=markup)


def send_digest(user_id, offset, sendmessage=True):
    channel_ids = bot_loop.run_until_complete(users.channels(user=user_id))
    if len(channel_ids) == 0:
        bot.send_message(
            user_id,
            "❌ Список каналов пуст! Используйте команду /add, чтобы добавить канал.",
        )
        return
    if sendmessage:
        bot.send_message(user_id, "📅 *Дайджест на сегодня:*", parse_mode="Markdown")

    headers = {"Content-type": "application/json"}
    data = make_data(
        str(user_id),
        bot_loop.run_until_complete(users.get_limit(user_id)),
        offset,
        channel_ids,
    )
    logger.info(f"Запрос дайджеста: {data}")
    response = requests.get("http://127.0.0.1:8000/tgdigest", headers=headers, json=data)

    if response.status_code != 200:
        bot.send_message(user_id, "⚠️ Не удалось получить дайджест.")
        return

    messages = response.json()
    bot_loop.run_until_complete(forward_messages(user_id, messages))


@bot.message_handler(commands=["digest"])
def digest_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    markup = telebot.types.InlineKeyboardMarkup()
    buttons = [
        telebot.types.InlineKeyboardButton(
            group_name, callback_data=f"digest${group_name}${user_id}"
        )
        for group_name in groups.keys()
    ]
    markup.add(*buttons)

    bot.send_message(
        user_id,
        "📂 *Выберите группу каналов для формирования дайджеста:*",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["settings"])
def settings_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/add", "/del")
    markup.row("/addFeed", "/delFeed")
    markup.row("/getlist", "/getGroups")
    markup.row("/addChannelGroup", "/back_to_main")

    settings_text = "*Настройки пользователя:*"
    bot.send_message(user_id, settings_text, reply_markup=markup, parse_mode="Markdown")


def get_title(channel_id):
    try:
        chat = bot.get_chat(channel_id)
        return chat.title
    except Exception as e:
        logger.error(f"Ошибка получения названия канала {channel_id}: {e}")
        return "Неизвестный канал"


@bot.message_handler(commands=["add"])
def add_channel_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        # Аргумент не указан
        bot.send_message(
            user_id,
            "Вы не указали канал! Отправьте сейчас в новом сообщении *только ID канала* (без /).",
            parse_mode="Markdown"
        )
        pending_commands[user_id] = "add"
        return

    channel_id = message_args[1]
    title = get_title(channel_id)
    if title == "Неизвестный канал":
        bot.send_message(user_id, "❌ Некорректное имя канала", parse_mode="Markdown")
        return

    bot_loop.run_until_complete(users.subscribe(login=user_id, channel=channel_id))

    markup = telebot.types.InlineKeyboardMarkup()
    buttons = [
        telebot.types.InlineKeyboardButton(
            group_name, callback_data=f"add${channel_id}${group_name}"
        )
        for group_name in groups.keys()
    ]
    markup.add(*buttons)

    bot.send_message(
        user_id,
        f"📂 В какую группу добавить канал *{title}*?",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["del"])
def del_channel_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        bot.send_message(
            user_id,
            "Вы не указали канал! Отправьте сейчас в новом сообщении *только ID канала* (без /).",
            parse_mode="Markdown"
        )
        pending_commands[user_id] = "del"
        return

    channel_id = message_args[1]
    title = get_title(channel_id)
    if title == "Неизвестный канал":
        bot.send_message(user_id, "❌ Некорректное имя канала", parse_mode="Markdown")
        return

    deleted = bot_loop.run_until_complete(users.unsubscribe(login=user_id, channel=channel_id))
    if not deleted:
        bot.send_message(
            user_id, f'❌ Канала "{title}" нет в списке!', parse_mode="Markdown"
        )
        return

    bot.send_message(
        user_id, f'✅ Канал "{title}" был удалён из списка.', parse_mode="Markdown"
    )


@bot.message_handler(commands=["addFeed"])
def add_feed_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        bot.send_message(
            user_id,
            "Вы не указали фид! Отправьте сейчас в новом сообщении *только URL фида* (без /).",
            parse_mode="Markdown"
        )
        pending_commands[user_id] = "addFeed"
        return

    feed = message_args[1]
    bot_loop.run_until_complete(users.subscribe(login=user_id, feed=feed))

    markup = telebot.types.InlineKeyboardMarkup()
    buttons = [
        telebot.types.InlineKeyboardButton(
            group_name, callback_data=f"add${feed}${group_name}"
        )
        for group_name in groups.keys()
    ]
    markup.add(*buttons)

    bot.send_message(
        user_id,
        f"📂 В какую группу добавить фид *{feed}*?",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["delFeed"])
def del_feed_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        bot.send_message(
            user_id,
            "Вы не указали фид! Отправьте сейчас отдельным сообщением *только URL фида* (без /).",
            parse_mode="Markdown"
        )
        pending_commands[user_id] = "delFeed"
        return

    feed = message_args[1]
    deleted = bot_loop.run_until_complete(users.unsubscribe(login=user_id, feed=feed))
    if not deleted:
        bot.send_message(user_id, f'❌ Фида "{feed}" нет в списке!', parse_mode="Markdown")
        return

    bot.send_message(
        user_id, f'✅ Фид "{feed}" был удалён из списка.', parse_mode="Markdown"
    )


@bot.message_handler(commands=["getlist"])
def get_list_bot(message)
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    channel_ids = bot_loop.run_until_complete(users.channels(user=user_id))
    if not channel_ids:
        bot.send_message(
            user_id,
            "❌ На данный момент ни одного канала не подключено!\nИспользуйте команду /add, чтобы добавить канал.",
        )
        return

    channels_text = "\n".join([f"• {cid} - {get_title(cid)}" for cid in channel_ids])
    bot.send_message(
        user_id,
        f"📃 *Список подключённых каналов:*\n{channels_text}",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["getGroups"])
def get_groups_list_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    if not groups:
        bot.send_message(user_id, "❌ Группы каналов отсутствуют.")
        return

    groups_text = "\n\n".join(
        [
            f"• *{group_name}* - " + ("Пусто" if not groupChannels else ", ".join(groupChannels))
            for group_name, groupChannels in groups.items()
        ]
    )
    bot.send_message(
        user_id,
        f"📂 *Список групп каналов:*\n\n{groups_text}",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["calibrate"])
def calibrate_bot(message):
    send_digest(message.from_user.id, date.today() - timedelta(days=3), False)
    bot.send_message(
        message.from_user.id,
        "🔧 Пройдем калибровку! Оцените сообщения выше, и мы подстроим всё под вас!",
    )


@bot.message_handler(commands=["exit"])
def exit_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/start")

    bot.send_message(
        user_id,
        "👋 Работа бота завершена. Напишите /start для повторного запуска.",
        reply_markup=markup,
    )


@bot.message_handler(commands=["addChannelGroup"])
def add_channel_group_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        bot.send_message(
            user_id,
            "Вы не указали название группы! Отправьте сейчас отдельным сообщением *только имя группы* (без /).",
            parse_mode="Markdown"
        )
        pending_commands[user_id] = "addChannelGroup"
        return

    group_name = message_args[1]
    if group_name in groups:
        bot.send_message(
            user_id, "❌ Группа с таким именем уже существует!", parse_mode="Markdown"
        )
        return

    groups[group_name] = []
    bot.send_message(
        user_id, f"✅ Группа *{group_name}* успешно создана!", parse_mode="Markdown"
    )


timesToSend = []
sended = {}


def clockWatcherRoutine():
    while True:
        sleep(60)
        current_time = datetime.now()
        for (u_id, hour, minute) in timesToSend:
            curr_date = current_time.date()
            if sended.get(u_id) == curr_date:
                continue
            if hour == current_time.hour and minute == current_time.minute:
                sended[u_id] = curr_date
                send_digest(
                    u_id,
                    date.today()
                    - timedelta(
                        days=bot_loop.run_until_complete(users.get_period(u_id)) or 1
                    ),
                )


clockWatcher = Thread(target=clockWatcherRoutine)
clockWatcher.setDaemon(True)
clockWatcher.start()


@bot.message_handler(commands=["setTime"])
def setTime_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        existing_time = None
        for (uid, h, m) in timesToSend:
            if uid == user_id:
                existing_time = f"{h:02d}:{m:02d}"
                break

        if existing_time:
            bot.send_message(
                user_id,
                f"Текущее время: {existing_time}\nОтправьте новое время отдельным сообщением (например, 10:30)."
            )
        else:
            bot.send_message(
                user_id,
                "Вы не указали время! Отправьте сейчас отдельным сообщением (например, 10:30)."
            )
        pending_commands[user_id] = "setTime"
        return

    try:
        hour, minute = map(int, message_args[1].split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        timesToSend.append((user_id, hour, minute))
        bot.send_message(
            user_id,
            f"⏰ Время отправки дайджеста установлено на {hour:02d}:{minute:02d}."
        )
    except (IndexError, ValueError):
        bot.send_message(
            user_id,
            "❌ Некорректный формат! Используйте /setTime hh:mm",
            parse_mode="Markdown",
        )


@bot.message_handler(commands=["setPeriod"])
def setPeriod_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        bot.send_message(
            user_id,
            "Вы не указали число дней! Отправьте сейчас отдельным сообщением (например, 2)."
        )
        pending_commands[user_id] = "setPeriod"
        return

    try:
        period = int(message_args[1])
        if period <= 0:
            raise ValueError
        if not bot_loop.run_until_complete(users.set_period(user_id, period)):
            raise RuntimeError("Не получилось сохранить период в БД")

        bot.send_message(
            user_id,
            f"📅 Частота отправки дайджеста установлена на каждые {period} дней.",
        )
    except (IndexError, ValueError):
        bot.send_message(
            user_id,
            "❌ Некорректный формат! Используйте /setPeriod n (где n - число дней)",
            parse_mode="Markdown",
        )
    except RuntimeError:
        bot.send_message(
            user_id,
            "❌ Не получилось установить период, попробуйте позже",
            parse_mode="Markdown",
        )


@bot.message_handler(commands=["setLimit"])
def setLimit_bot(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    message_args = message.text.split()
    if len(message_args) < 2:
        bot.send_message(
            user_id,
            "Вы не указали число новостей! Отправьте сейчас отдельным сообщением (например, 5)."
        )
        pending_commands[user_id] = "setLimit"
        return

    try:
        limit = int(message_args[1])
        if limit <= 0:
            raise ValueError
        if not bot_loop.run_until_complete(users.set_limit(user_id, limit)):
            raise RuntimeError("Не получилось сохранить лимит в БД")

        bot.send_message(
            user_id,
            f"#️⃣ Размер дайджеста установлен на {limit}.",
        )
    except (IndexError, ValueError):
        bot.send_message(
            user_id,
            "❌ Некорректный формат! Используйте /setLimit n (где n - число новостей)",
            parse_mode="Markdown",
        )
    except RuntimeError:
        bot.send_message(
            user_id,
            "❌ Не получилось установить лимит, попробуйте позже",
            parse_mode="Markdown",
        )


@bot.message_handler(func=lambda message: message.text == "/back_to_main")
def back_to_main(message):
    user_id = message.from_user.id
    if not bot_loop.run_until_complete(users.check_user(login=user_id)):
        return

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/help", "/digest")
    markup.row("/settings", "/exit")
    bot.send_message(user_id, "🔙 Вернулись в главное меню.", reply_markup=markup)

@bot.message_handler(func=lambda m: not m.text.startswith("/"))
def handle_pending_arguments(message):
    user_id = message.from_user.id
    if user_id not in pending_commands:
        return

    command_waiting = pending_commands[user_id]
    user_input = message.text.strip()

    del pending_commands[user_id]

    fake_message = telebot.types.Message(
        message_id=message.message_id,
        from_user=message.from_user,
        chat=message.chat,
        date=message.date,
        content_type=message.content_type,
        options={},
        json_string="{}"
    )
    fake_message.text = f"/{command_waiting} {user_input}"

    if command_waiting == "add":
        add_channel_bot(fake_message)
    elif command_waiting == "del":
        del_channel_bot(fake_message)
    elif command_waiting == "addFeed":
        add_feed_bot(fake_message)
    elif command_waiting == "delFeed":
        del_feed_bot(fake_message)
    elif command_waiting == "addChannelGroup":
        add_channel_group_bot(fake_message)
    elif command_waiting == "setTime":
        setTime_bot(fake_message)
    elif command_waiting == "setPeriod":
        setPeriod_bot(fake_message)
    elif command_waiting == "setLimit":
        setLimit_bot(fake_message)

bot.infinity_polling()
