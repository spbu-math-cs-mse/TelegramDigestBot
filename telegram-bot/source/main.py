import telebot

with open("token.txt", "r") as f:
    TOKEN = f.readline()

bot = telebot.TeleBot(TOKEN)

command_list_help = ["/start - начать работу",
    "/help - вывести список команд",
    "/setTime hh:mm - установить время отправки дайджеста (в формате час:минута)",
    "/setPeriod n - установить частоту отправки дайджеста (n в днях)",
    "/digest - получить дайджест",
    "/settings - вывести команды для пользовательских настроек",
    "/exit - завершить работу",]
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

timesToSend = []
periodsToSend = []

def clockWatcherRoutine():
    while True:
        sleep(1)
        for user_id, hour, minute in timesToSend:
           if hour == datetime.datetime.now().hour and minute == datetime.datetime.now().minute:
               send_digest(user_id)


clockWatcher = Thread(target = clockWatcherRoutine)
clockWatcher.setDaemon(True)
clockWatcher.start()

@bot.message_handler(commands=["setTime"])
def setTime_bot(message):
    user_id = message.from_user.id
    date = message.text.split(":")
    timesToSend.append((user_id, int(date[0]), int(date[1])))

@bot.message_handler(commands=["setPeriod"])
def setPeriod_bot(message):
    user_id = message.from_user.id
    period = message.text
    periodsToSend.append(period)

bot.infinity_polling()
