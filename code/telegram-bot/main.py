import telebot
from telethon import TelegramClient
import requests
import json
from datetime import date, timedelta, datetime

with open("token.txt", "r") as f:
    TOKEN = f.readline()

with open("credentials.txt", "r") as f:
    api_id_bot = int(f.readline())
    api_hash_bot = f.readline()

bot = telebot.TeleBot(TOKEN)
client_bot = TelegramClient(
    "bot", api_id_bot, api_hash_bot, system_version="4.16.30-vxCUSTOM"
).start(bot_token=TOKEN)
bot_loop = client_bot.loop


command_list_help = [
    "/start - начать работу",
    "/help - вывести список команд",
    "/digest - получить дайджест",
    "/settings - вывести команды для пользовательских настроек",
    "/exit - завершить работу",
]

command_list_settings = [
    "/add <id канала> - подключить канал к дайджесту",
    "/getlist - получить список подключенных каналов",
    "/del <id канала> - отключить канал от дайджеста",
]

is_started = False

channel_ids = set()


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
    bot.send_message(
        message.from_user.id, "Привет! Напиши /help для вывода списка команд."
    )


@bot.message_handler(commands=["help"])
def help_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "\n\n".join(command_list_help))


async def forward_messages(user_id, messages):
    for message in messages:
        await client_bot.forward_messages(user_id, message["id"], message["channel"])


def make_data(user_id: str, limit: int, offset_date: datetime, channel_ids):
    return json.dumps(
        {
            "user_id": user_id,
            "limit": limit,
            "offset_date": str(offset_date),
            "channels": [{"id": id} for id in channel_ids],
        }
    )


@bot.message_handler(commands=["digest"])
def digest_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id
    if len(channel_ids) == 0:
        bot.send_message(
            user_id,
            "Список каналов пуст! "
            "Воспользуйтесь командой /add, чтобы добавить канал.",
        )
        return
    bot.send_message(user_id, "Дайджест на сегодня:")
    headers = {"Content-type": "application/json"}
    response = requests.get(
        "http://127.0.0.1:8000/digest",
        headers=headers,
        data=make_data(str(user_id), 5, date.today() - timedelta(days=1), channel_ids),
    )
    if response.status_code != 200:
        bot.send_message(user_id, "Не получилось получить дайджест")
        return
    messages = response.json()
    bot_loop.run_until_complete(forward_messages(user_id, messages))


@bot.message_handler(commands=["settings"])
def settings_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "\n\n".join(command_list_settings))


def get_title(channel_id):
    return bot.get_chat(channel_id).title


@bot.message_handler(commands=["add"])
def add_bot(message):
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
    channel_ids.add(channel_id)
    bot.send_message(user_id, f'Канал "{get_title(channel_id)}" добавлен в список.')


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
    if channel_id not in channel_ids:
        bot.send_message(user_id, f'Канала "{get_title(channel_id)}" нет в списке!')
        return
    channel_ids.remove(channel_id)
    bot.send_message(user_id, f'Канал "{get_title(channel_id)}" был удален из списка.')


@bot.message_handler(commands=["getlist"])
def get_list_bot(message):
    if not is_started:
        return
    user_id = message.from_user.id
    if len(channel_ids) == 0:
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


@bot.message_handler(commands=["exit"])
def exit_bot(message):
    if not is_started:
        return
    exit_actions()


bot.infinity_polling()
