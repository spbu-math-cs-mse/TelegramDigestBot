from telethon.sync import TelegramClient
from telethon import functions, types
from flask import Flask, request

with open("credentials.txt", "r") as f:
    api_id = int(f.readline())
    api_hash = f.readline()

client = TelegramClient("system", api_id, api_hash)
loop = client.loop

app = Flask(__name__)

async def ranking_impl(request):
    limit = int(request.args.get("limit", 5))
    buffer = []
    for entry in request.json:
        channel = entry["channel"]
        ids = entry["ids"]
        size = (await client(functions.channels.GetFullChannelRequest(
            channel=channel
        ))).full_chat.participants_count
        views = (await client(functions.messages.GetMessagesViewsRequest(
        peer=channel,
        id=ids,
        increment=False
        ))).views
        for i in range(len(views)):
            buffer.append((views[i].views / size, channel, ids[i]))
    buffer.sort(reverse=True)
    return [{"channel": channel, "id": id} for (_, channel, id) in buffer[:limit]]

@app.route("/ranking", methods=["GET"])
def ranking():
    result = loop.run_until_complete(ranking_impl(request))
    return result

if __name__ == '__main__':
    with client:
        app.run(port=3001)
