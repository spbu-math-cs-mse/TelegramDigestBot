from telethon import TelegramClient, functions
from fastapi import Query, Body, FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager
from datetime import datetime

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


class Request(BaseModel):
    user_id: str
    limit: int
    offset_date: datetime
    channels: list[Channel]


@app.get("/digest")
async def digest(request: Request = Body()):
    limit = request.limit
    offset_date = request.offset_date
    channels = request.channels
    buffer = []
    for channel in channels:
        size = (
            await client(functions.channels.GetFullChannelRequest(channel=channel.id))
        ).full_chat.participants_count
        async for message in client.iter_messages(
            channel.id, limit, offset_date=offset_date, reverse=True
        ):
            buffer.append((message.views / size, channel.id, message.id))
    buffer.sort(reverse=True)
    return [{"channel": channel, "id": id} for (_, channel, id) in buffer[:limit]]