import telebot

with open("token.txt", "r") as f:
    TOKEN = f.readline()

bot = telebot.TeleBot(TOKEN)

command_list_help = ["/start - начать работу",
                     "/help - вывести список команд",
                     "/exit - завершить работу"]
is_started = False


def start():
    global is_started
    is_started = True


def exit():
    global is_started
    is_started = False


@bot.message_handler(commands=['start'])
def start_bot(message):
    if not is_started:
        start()
        bot.send_message(message.from_user.id, "Привет! Напиши /help для вывода списка команд.")


@bot.message_handler(commands=['help'])
def help_bot(message):
    if not is_started:
        return
    bot.send_message(message.from_user.id, "\n\n".join(command_list_help))


@bot.message_handler(commands=['exit'])
def exit_bot(message):
    if is_started:
        exit()


bot.infinity_polling()