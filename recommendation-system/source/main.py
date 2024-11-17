import uvicorn
import asyncio
import aiosqlite
from telethon import TelegramClient, functions
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from contextlib import asynccontextmanager

DB_PATH = "recommendation-system.db"

with open("assets/credentials.txt", "r") as f:
    api_id = int(f.readline())
    api_hash = f.readline().strip()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
client = TelegramClient("recommendation-system", api_id, api_hash, loop=loop)
client.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS channels(
        name TEXT                 
        )
        """
        )
        await db.execute(
            """
        CREATE INDEX IF NOT EXISTS channels_index
        ON channels(name)
        """
        )
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS users(
        name TEXT                 
        )
        """
        )
        await db.execute(
            """
        CREATE INDEX IF NOT EXISTS users_index
        ON users(name)
        """
        )
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS likes(
            channel_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY(channel_id, message_id, user_id)
        )
        """
        )
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS dislikes(
            channel_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY(channel_id, message_id, user_id)
        )
        """
        )
        await db.commit()
    yield


app = FastAPI(lifespan=lifespan)


class Channel(BaseModel):
    id: str


class DigestRequest(BaseModel):
    user_id: str
    limit: int
    offset_date: datetime
    channels: list[Channel]


def get_score(message):
    return (
        message.views
        + len(message.reactions.results) * 5
        + message.replies.replies * 10
    )


@app.get("/digest")
async def digest(request: DigestRequest):
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
            buffer.append((get_score(message) / size, channel.id, message.id))
    buffer.sort(reverse=True)
    return [{"channel": channel, "id": id} for (_, channel, id) in buffer[:limit]]


class LikeRequest(BaseModel):
    user_id: str
    channel: Channel
    id: int


async def get_user(db: aiosqlite.Connection, user_id: str) -> int:
    cursor = await db.execute(f"SELECT rowid FROM users WHERE name = '{user_id}'")
    row = await cursor.fetchone()
    if row is not None:
        return row[0]
    cursor = await db.execute(f"INSERT INTO users VALUES('{user_id}') RETURNING rowid")
    row = await cursor.fetchone()
    await db.commit()
    return row[0]


async def get_channel(db: aiosqlite.Connection, channel_id: str) -> int:
    cursor = await db.execute(f"SELECT rowid FROM channels WHERE name = '{channel_id}'")
    row = await cursor.fetchone()
    if row is not None:
        return row[0]
    cursor = await db.execute(
        f"INSERT INTO channels VALUES('{channel_id}') RETURNING rowid"
    )
    row = await cursor.fetchone()
    await db.commit()
    return row[0]


@app.post("/like")
async def like(request: LikeRequest):
    async with aiosqlite.connect(DB_PATH) as db:
        ss = f"INSERT OR IGNORE INTO likes VALUES({await get_channel(db, request.channel.id)}, {request.id}, {await get_user(db, request.user_id)})"
        print(ss)
        await db.execute(ss)
        await db.commit()
    return {}


class DislikeRequest(BaseModel):
    user_id: str
    channel: Channel
    id: int


@app.post("/dislike")
async def dislike(request: DislikeRequest):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"INSERT OR IGNORE INTO dislikes VALUES({await get_channel(db, request.channel.id)}, {request.id}, {await get_user(db, request.user_id)})"
        )
        await db.commit()
    return {}


if __name__ == "__main__":
    config = uvicorn.Config(app=app)
    server = uvicorn.Server(config)
    loop.create_task(server.serve())
    loop.run_forever()
