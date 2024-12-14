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
    "/getlist - Получить список подключенных каналов",
    "/getGroups - Получить список групп каналов",
    "/del <id канала> - Отключить канал от дайджеста",
    "/addChannelGroup <название группы каналов> - Создать группу каналов",
]

is_started = False

users = bot_loop.run_until_complete(UserService().init("127.0.0.1", 5000))


def start_actions():
    global is_started
    is_started = True


def exit_actions():
    global is_started
    is_started = False


@bot.message_handler(commands=["start"])
def start_bot(message):
    if is_started:
        return
    start_actions()

    bot_loop.run_until_complete(
        users.register_user(login=message.from_user.id, name=str(message.from_user.id))
    )

    # Создание главной клавиатуры
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
    if not is_started:
        return
    help_text = "*Список доступных команд:*\n\n" + "\n".join(command_list_help)

    # Добавление кнопки для быстрого доступа к настройкам
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("⚙️ Настройки", callback_data="open_settings")
    )

    bot.send_message(
        message.from_user.id, help_text, reply_markup=markup, parse_mode="Markdown"
    )


def send_reaction_buttons(user_id, entity_id):
    metadata = f"{user_id},{entity_id}"
    markup = telebot.types.InlineKeyboardMarkup()
    btn_yes = telebot.types.InlineKeyboardButton("👍", callback_data=f"like_{metadata}")
    btn_no = telebot.types.InlineKeyboardButton(
        "👎", callback_data=f"dislike_{metadata}"
    )
    markup.add(btn_yes, btn_no)

    bot.send_message(user_id, "Понравилось? Оцените ниже:", reply_markup=markup)


async def forward_messages(user_id, messages):
    for message in messages:
        bot.send_message(user_id, message["description"] + "\n" + message["link"])
        send_reaction_buttons(user_id, message["entity_id"])


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

limit = 5


@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    headers = {"Content-type": "application/json"}
    if call.data.startswith("like"):
        buffer = call.data[5:].split(",")
        data = {"user": buffer[0], "entity_id": int(buffer[1])}
        response = requests.post(
            "http://127.0.0.1:8000/dislike",
            headers=headers,
            json=data,
        )
        bot.answer_callback_query(call.id, "Спасибо за вашу оценку! 👍")
    elif call.data.startswith("dislike"):
        buffer = call.data[8:].split(",")
        data = {"user": buffer[0], "entity_id": int(buffer[1])}
        response = requests.post(
            "http://127.0.0.1:8000/dislike",
            headers=headers,
            json=data,
        )
        bot.answer_callback_query(call.id, "Учтём ваши замечания! 🙁")
    elif call.data.startswith("add"):
        _, channel_id, group_name = call.data.split("$")
        groups[group_name].append(channel_id)
        bot.answer_callback_query(call.id, "Канал успешно добавлен! ✅")
    elif call.data.startswith("digest"):
        _, group_name, user_id = call.data.split("$")
        bot.answer_callback_query(call.id, "Дайджест генерируется... ⏳")
        global periodsToSend
        send_digest(
            int(user_id),
            date.today() - timedelta(days=periodsToSend.get(int(user_id), 1)),
            True,
        )
    elif call.data == "open_settings":
        # Отправка меню настроек
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("/add", "/del")
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

    data = make_data(str(user_id), limit, offset, channel_ids)
    logger.info(f"Запрос дайджеста: {data}")

    response = requests.get(
        "http://127.0.0.1:8000/tgdigest",
        headers=headers,
        json=data,
    )
    if response.status_code != 200:
        bot.send_message(user_id, "⚠️ Не удалось получить дайджест.")
        return
    messages = response.json()
    bot_loop.run_until_complete(forward_messages(user_id, messages))


@bot.message_handler(commands=["digest"])
def digest_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id
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
    if not is_started:
        return
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/add", "/del")
    markup.row("/getlist", "/getGroups")
    markup.row("/addChannelGroup", "/back_to_main")

    settings_text = "*Настройки пользователя:*"
    bot.send_message(
        message.from_user.id, settings_text, reply_markup=markup, parse_mode="Markdown"
    )


def get_title(channel_id):
    try:
        chat = bot.get_chat(channel_id)
        return chat.title
    except Exception as e:
        logger.error(f"Ошибка получения названия канала {channel_id}: {e}")
        return "Неизвестный канал"


@bot.message_handler(commands=["add"])
def add_bot(message):
    global groups

    if not is_started:
        return
    user_id = message.from_user.id
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(
            user_id,
            "❌ Некорректные входные данные!\n*Формат:* /add <id канала>",
            parse_mode="Markdown",
        )
        return
    channel_id = message_args[1]
    title = get_title(channel_id)
    if title == "Неизвестный канал":
        bot.send_message(user_id, "❌ Некорректное имя канала", parse_mode="Markdown")
        return
    bot_loop.run_until_complete(users.subscribe(user=user_id, channel=channel_id))

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
def del_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(
            user_id,
            "❌ Некорректные входные данные!\n*Формат:* /del <id канала>",
            parse_mode="Markdown",
        )
        return
    channel_id = message_args[1]
    title = get_title(channel_id)
    if title == "Неизвестный канал":
        bot.send_message(user_id, "❌ Некорректное имя канала", parse_mode="Markdown")
        return
    deleted = bot_loop.run_until_complete(
        users.unsubscribe(user=user_id, channel=channel_id)
    )
    if not deleted:
        bot.send_message(
            user_id, f'❌ Канала "{title}" нет в списке!', parse_mode="Markdown"
        )
        return
    bot.send_message(
        user_id, f'✅ Канал "{title}" был удалён из списка.', parse_mode="Markdown"
    )


@bot.message_handler(commands=["getlist"])
def get_list_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id

    channel_ids = bot_loop.run_until_complete(users.channels(user=user_id))

    if channel_ids is None or len(channel_ids) == 0:
        bot.send_message(
            user_id,
            "❌ На данный момент ни одного канала не подключено!\nИспользуйте команду /add, чтобы добавить канал.",
        )
        return
    channels_text = "\n".join(
        [f"• {channel_id} - {get_title(channel_id)}" for channel_id in channel_ids]
    )
    bot.send_message(
        user_id,
        f"📃 *Список подключённых каналов:*\n{channels_text}",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["getGroups"])
def get_groups_list_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id

    global groups

    if not groups:
        bot.send_message(user_id, "❌ Группы каналов отсутствуют.")
        return

    groups_text = "\n\n".join(
        [
            f"• *{group_name}* - "
            + ("Пусто" if not groupChannels else ", ".join(groupChannels))
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
        "🔧 Пройдем калибровку! Оцените сообщения выше, и мы подстроим все под вас!",
    )


@bot.message_handler(commands=["exit"])
def exit_bot(message):
    if not is_started:
        return
    exit_actions()
    # Возврат к главной клавиатуре после выхода
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/start")
    bot.send_message(
        message.from_user.id,
        "👋 Работа бота завершена. Напишите /start для повторного запуска.",
        reply_markup=markup,
    )


@bot.message_handler(commands=["addChannelGroup"])
def add_channel_group_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(
            user_id,
            "❌ Некорректные входные данные!\n*Формат:* /addChannelGroup <название группы каналов>",
            parse_mode="Markdown",
        )
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
periodsToSend = {}
sended = {}


def clockWatcherRoutine():
    while True:
        sleep(60)
        current_time = datetime.now()
        for user_id, hour, minute in timesToSend:
            curr_date = current_time.date()
            if sended.get(user_id) == curr_date:
                continue
            if hour == current_time.hour and minute == current_time.minute:
                sended[user_id] = curr_date
                send_digest(
                    user_id,
                    date.today() - timedelta(days=periodsToSend.get(user_id, 1)),
                )


clockWatcher = Thread(target=clockWatcherRoutine)
clockWatcher.setDaemon(True)
clockWatcher.start()


@bot.message_handler(commands=["setTime"])
def setTime_bot(message):
    user_id = message.from_user.id
    try:
        time_str = message.text.split()[1]
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        timesToSend.append((user_id, hour, minute))
        bot.send_message(
            user_id,
            f"⏰ Время отправки дайджеста установлено на {hour:02d}:{minute:02d}.",
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
    try:
        period = int(message.text.split()[1])
        if period <= 0:
            raise ValueError
        periodsToSend[user_id] = period
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


@bot.message_handler(commands=["setLimit"])
def setLimit_bot(message):
    user_id = message.from_user.id
    try:
        parsed = int(message.text.split()[1])
        if parsed <= 0:
            raise ValueError
        global limit
        limit = parsed
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


# Обработка кнопки возврата к главной клавиатуре из настроек
@bot.message_handler(func=lambda message: message.text == "/back_to_main")
def back_to_main(message):
    if not is_started:
        return
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/help", "/digest")
    markup.row("/settings", "/exit")
    bot.send_message(
        message.from_user.id, "🔙 Вернулись в главное меню.", reply_markup=markup
    )


bot.infinity_polling()
