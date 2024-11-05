from telethon import TelegramClient, functions
from fastapi import Query, Body, FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager

with open("credentials.txt", "r") as f:
    api_id = int(f.readline())
    api_hash = f.readline()

client = TelegramClient("system", api_id, api_hash)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.connect()
    yield


app = FastAPI(lifespan=lifespan)


class Channel(BaseModel):
    id: str


async def ranking_impl(limit: int, channels: list[Channel]):
    buffer = []
    for channel in channels:
        size = (
            await client(functions.channels.GetFullChannelRequest(channel=channel.id))
        ).full_chat.participants_count
        async for message in client.iter_messages(channel.id, limit):
            buffer.append((message.views / size, channel.id, message.id))
    buffer.sort(reverse=True)
    return [{"channel": channel, "id": id} for (_, channel, id) in buffer[:limit]]


@app.get("/ranking")
async def ranking(limit: int = Query(5), channels: list[Channel] = Body()):
    result = await ranking_impl(limit, channels)
    return result
