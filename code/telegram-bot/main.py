import telebot
from telethon import TelegramClient

with open("token.txt", "r") as f:
    TOKEN = f.readline()

with open("credentials.txt", "r") as f:
    api_id_bot = int(f.readline())
    api_hash_bot = f.readline()

bot = telebot.TeleBot(TOKEN)
client_user = TelegramClient("system", api_id_bot, api_hash_bot, system_version='4.16.30-vxCUSTOM').start()
client_bot = TelegramClient("system2", api_id_bot, api_hash_bot, system_version='4.16.30-vxCUSTOM').start(bot_token=TOKEN)
user_loop = client_user.loop
bot_loop = client_bot.loop


command_list_help = ["/start - начать работу",
                     "/help - вывести список команд",
                     "/digest - получить дайджест",
                     "/settings - вывести команды для пользовательских настроек",
                     "/exit - завершить работу"]

command_list_settings = ["/add <тег канала> - подключить канал к дайджесту",
                         "/getlist - получить список подключенных каналов",
                         "/del <тег канала> - отключить канал от дайджеста"]

is_started = False

channel_ids = set()


def start_actions():
    global is_started
    is_started = True


def exit_actions():
    global is_started
    is_started = False
    client_user.log_out()
    client_bot.log_out()


@bot.message_handler(commands=['start'])
def start_bot(message):
    if is_started:  # на следующем спринте уберу эти проверки
        return
    start_actions()
    bot.send_message(message.from_user.id, "Привет! Напиши /help для вывода списка команд.")


@bot.message_handler(commands=['help'])
def help_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "\n\n".join(command_list_help))


async def get_messages(channel_id, cnt):
    entity = await client_user.get_input_entity(channel_id)
    messages = [target_message async for target_message in client_user.iter_messages(entity, limit=cnt)]
    return messages


async def forward_messages(channel_id, user_id, messages):
    await client_bot.forward_messages(user_id, messages, channel_id)


@bot.message_handler(commands=['digest'])
def digest_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "Дайджест на сегодня:")
    for channel_id in channel_ids:
        messages = user_loop.run_until_complete(get_messages(channel_id, 3))
        bot_loop.run_until_complete(forward_messages(channel_id, message.from_user.id, messages))


@bot.message_handler(commands=['settings'])
def settings_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "\n\n".join(command_list_settings))


@bot.message_handler(commands=['add'])
def add_bot(message):
    if not is_started:
        return
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(message.from_user.id, "Некорректные входные данные!")
        return
    channel_id = message_args[1]
    channel_ids.add(channel_id)


@bot.message_handler(commands=['getlist'])
def get_list_bot(message):
    if not is_started:
        return
    if len(channel_ids) == 0:
        bot.send_message(message.from_user.id, "На данный момент ни одного канала не подключено! "
                                               "Для подключения канала воспользуйтесь командой /add.")
    bot.send_message(message.from_user.id, "\n\n".join(
        [channel_id + " - " + bot.get_chat(channel_id).title for channel_id in channel_ids]))


@bot.message_handler(commands=['del'])
def del_bot(message):
    if not is_started:
        return
    message_args = message.text.split()
    if len(message_args) != 2:
        bot.send_message(message.from_user.id, "Некорректные входные данные!")
        return
    channel_id = message_args[1]
    if channel_id in channel_ids:
        channel_ids.remove(channel_id)
        bot.send_message(message.from_user.id, f"Канал {channel_id} был удален из списка.")
    else:
        bot.send_message(message.from_user.id, f"Канала {channel_id} нет в списке!")


@bot.message_handler(commands=['exit'])
def exit_bot(message):
    if not is_started:
        return
    exit_actions()


bot.infinity_polling()

