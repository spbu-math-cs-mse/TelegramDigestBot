import telebot
from telethon import TelegramClient
import requests
from time import sleep
from datetime import date, timedelta, datetime
from users import UserService
from threading import *

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
    "/start - начать работу",
    "/help - вывести список команд",
    "/setTime - установить время отправки дайджеста (в формате час:минута)",
    "/setPeriod - установить частоту отправки дайджеста (в днях)",
    "/digest - получить дайджест",
    "/settings - вывести команды для пользовательских настроек",
    "/exit - завершить работу",
]

command_list_settings = [
    "/add <id канала> - подключить канал к дайджесту",
    "/getlist - получить список подключенных каналов",
    "/getGroups - получить список групп каналов",
    "/del <id канала> - отключить канал от дайджеста",
    "/addChannelGroup <название группы каналов> - создать группу каналов",
]

command_list_help = [
    "/start - начать работу",
    "/help - вывести список команд",
    "/setTime hh:mm - установить время отправки дайджеста (в формате час:минута)",
    "/setPeriod n - установить частоту отправки дайджеста (n в днях)",
    "/digest - получить дайджест",
    "/settings - вывести команды для пользовательских настроек",
    "/exit - завершить работу",
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
    if is_started:  # на следующем спринте уберу эти проверки
        return
    start_actions()

    bot_loop.run_until_complete(
        users.register_user(login=message.from_user.id, name=message.from_user.id)
    )

    bot.send_message(
        message.from_user.id, "Привет! Напиши /help для вывода списка команд."
    )


@bot.message_handler(commands=["help"])
def help_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "\n\n".join(command_list_help))


def send_reaction_buttons(user_id, message_id, channel_id):
    metadata = f"{user_id},{message_id},{channel_id}"
    markup = telebot.types.InlineKeyboardMarkup()
    btn_yes = telebot.types.InlineKeyboardButton("👍", callback_data=f'like_{metadata}')
    btn_no = telebot.types.InlineKeyboardButton("👎", callback_data=f'dislike_{metadata}')
    markup.add(btn_yes, btn_no)
    
    bot.send_message(user_id, "Понравилось?", reply_markup=markup)

async def forward_messages(user_id, messages):
    for message in messages:
        await client_bot.forward_messages(user_id, message["id"], message["channel"])
        send_reaction_buttons(user_id, message["id"], message["channel"])


def make_data(user_id: str, limit: int, offset_date: datetime, channel_ids):
    return {
        "user_id": user_id,
        "limit": limit,
        "offset_date": str(offset_date),
        "channels": [{"id": id} for id in channel_ids],
    }


groups = {
    "По умолчанию": [],
}


@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data.startswith('like'):
        bot.answer_callback_query(call.id, "Вам понравилось, мы рады!")
    elif call.data.startswith('dislike'):
        bot.answer_callback_query(call.id, "Учтем ваши замечания!")
    elif call.data.startswith('add'):
        global groups
        groups[call.data.split('$')[2]].append(call.data.split('$')[1])
        bot.answer_callback_query(call.id, "Канал успешно добавлен!")
    elif call.data.startswith('digest'):
        bot.answer_callback_query(call.id, "Дайджест успешно сгенерирован!")
        send_digest(int(call.data.split('$')[2]), date.today() - timedelta(days=1), True)

def send_digest(user_id, offset, sendmessage=True):
    channel_ids = bot_loop.run_until_complete(users.channels(user=user_id))

    if len(channel_ids) == 0:
        bot.send_message(
            user_id,
            "Список каналов пуст! "
            "Воспользуйтесь командой /add, чтобы добавить канал.",
        )
        return
    if sendmessage:
        bot.send_message(user_id, "Дайджест на сегодня:")
    headers = {"Content-type": "application/json"}

    data = make_data(str(user_id), 5, offset, channel_ids)
    logger.warning(data)

    response = requests.get(
        "http://127.0.0.1:8000/digest",
        headers=headers,
        json=data,
    )
    if response.status_code != 200:
        bot.send_message(user_id, "Не получилось получить дайджест")
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
        telebot.types.InlineKeyboardButton(group_name, callback_data=f'digest${group_name}${user_id}') 
        for group_name in groups.keys()
    ]
    markup.add(*buttons)

    bot.send_message(user_id, "Для какой группы каналов формируем дайджест?", reply_markup=markup)


@bot.message_handler(commands=["settings"])
def settings_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "\n\n".join(command_list_settings))


def get_title(channel_id):
    return bot.get_chat(channel_id).title


@bot.message_handler(commands=["add"])
def add_bot(message):
    global groups

    if not is_started:
        return
    user_id = message.from_user.id
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(
            user_id, "Некорректные входные данные! Формат: /add <id канала>."
        )
        return
    channel_id = message_args[1]
    bot_loop.run_until_complete(users.subscribe(user=user_id, channel=channel_id))

    markup = telebot.types.InlineKeyboardMarkup()

    buttons = [
        telebot.types.InlineKeyboardButton(group_name, callback_data=f'add${channel_id}${group_name}') 
        for group_name in groups.keys()
    ]

    markup.add(*buttons)

    bot.send_message(user_id, f'В какую группу добавить ?', reply_markup=markup)


@bot.message_handler(commands=["del"])
def del_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(
            user_id, "Некорректные входные данные! Формат: /del <id канала>."
        )
        return
    channel_id = message_args[1]
    deleted = bot_loop.run_until_complete(
        users.unsubscribe(user=user_id, channel=channel_id)
    )
    if not deleted:
        bot.send_message(user_id, f'Канала "{get_title(channel_id)}" нет в списке!')
        return
    bot.send_message(user_id, f'Канал "{get_title(channel_id)}" был удален из списка.')


@bot.message_handler(commands=["getlist"])
def get_list_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id

    channel_ids = bot_loop.run_until_complete(users.channels(user=user_id))

    if channel_ids is None or len(channel_ids) == 0:
        bot.send_message(
            user_id,
            "На данный момент ни одного канала не подключено! "
            "Для подключения канала воспользуйтесь командой /add.",
        )
        return
    bot.send_message(
        user_id,
        "\n\n".join(
            [channel_id + " - " + get_title(channel_id) for channel_id in channel_ids]
        ),
    )


@bot.message_handler(commands=["getGroups"])
def get_groups_list_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id

    global groups

    bot.send_message(
        user_id,
        "На данный момент вы добавили следующие группы:\n\n" + "\n\n".join(
            [groupName + " - " + ("Пусто" if not groupChannels else ', '.join(groupChannels)) for groupName, groupChannels in groups.items()]
        ),
    )

@bot.message_handler(commands=["calibrate"])
def calibrate_bot(message):
    send_digest(message.from_user.id, date.today() - timedelta(days=3), False)
    bot.send_message(message.from_user.id, "Пройдем калиброку! Оцените сообщения выше и мы подстроим все под вас!")



@bot.message_handler(commands=["exit"])
def exit_bot(message):
    if not is_started:
        return
    exit_actions()



@bot.message_handler(commands=["addChannelGroup"])
def add_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(
            user_id, "Некорректные входные данные! Формат: /addChannelGroup <название группы каналов>."
        )
        return
    group_name = message_args[1]
    if group_name in groups:
        bot.send_message(
            user_id, "Группа с таким именем уже существует!"
        )
        return
    bot.send_message(user_id, f'Группа {group_name} успешно создана!')
    groups[group_name] = []


timesToSend = []
periodsToSend = []
sended = {}


def clockWatcherRoutine():
    while True:
        sleep(1)
        for user_id, hour, minute in timesToSend:
            curr = datetime.now().date()
            if sended.get(user_id) == curr:  # already sent today
                continue
            if hour == datetime.now().hour and minute == datetime.now().minute:
                sended[user_id] = curr
                send_digest(user_id, date.today() - timedelta(days=1))


clockWatcher = Thread(target=clockWatcherRoutine)
clockWatcher.setDaemon(True)
clockWatcher.start()


@bot.message_handler(commands=["setTime"])
def setTime_bot(message):
    user_id = message.from_user.id
    date = message.text[9:].split(":")
    timesToSend.append((user_id, int(date[0]), int(date[1])))


@bot.message_handler(commands=["setPeriod"])
def setPeriod_bot(message):
    user_id = message.from_user.id
    period = message.text[10:]
    periodsToSend.append(period)

bot.infinity_polling()
