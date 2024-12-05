import uvicorn
import asyncio
import aiosqlite
from telethon import TelegramClient, functions
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from contextlib import asynccontextmanager
from math import sqrt
import os
from openai import OpenAI
import feedparser
import pytz
import random

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
        CREATE TABLE IF NOT EXISTS entities(
        link TEXT
        )
        """
        )
        await db.execute(
            """
        CREATE INDEX IF NOT EXISTS entities_index
        ON entities(link)
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
            entity_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY(entity_id, user_id)
        )
        """
        )
        await db.execute(
            """
        CREATE TABLE IF NOT EXISTS dislikes(
            entity_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY(entity_id, user_id)
        )
        """
        )
        await db.commit()
    yield


async def get_user(db: aiosqlite.Connection, user: str) -> int:
    cursor = await db.execute(f"SELECT rowid FROM users WHERE name = '{user}'")
    row = await cursor.fetchone()
    if row is not None:
        return row[0]
    cursor = await db.execute(f"INSERT INTO users VALUES('{user}') RETURNING rowid")
    row = await cursor.fetchone()
    await db.commit()
    return row[0]


async def get_entity(db: aiosqlite.Connection, link: str, skip: bool = False) -> int:
    cursor = await db.execute(f"SELECT rowid FROM entities WHERE link = '{link}'")
    row = await cursor.fetchone()
    if row is not None:
        return row[0]
    if skip:
        return 0
    cursor = await db.execute(f"INSERT INTO entities VALUES('{link}') RETURNING rowid")
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


async def get_likes(db: aiosqlite.Connection, entity_id: int) -> int:
    cursor = await db.execute(f"SELECT COUNT(*) FROM likes WHERE entity_id={entity_id}")
    row = await cursor.fetchone()
    return row[0]


async def get_dislikes(db: aiosqlite.Connection, entity_id: int) -> int:
    cursor = await db.execute(
        f"SELECT COUNT(*) FROM dislikes WHERE entity_id={entity_id}"
    )
    row = await cursor.fetchone()
    return row[0]


app = FastAPI(lifespan=lifespan)


class Channel(BaseModel):
    name: str


class TGDigestRequest(BaseModel):
    user: str
    limit: int
    offset_date: datetime
    channels: list[Channel]


def get_popularity_score(message) -> int:
    if message.reactions is None:
        return message.views + message.replies.replies * 10

    return (
        message.views
        + len(message.reactions.results) * 5
        + message.replies.replies * 10
    )


def get_wilson_score(likes, dislikes) -> float:
    if likes == 0:
        return -dislikes
    z = 1.64485
    n = likes + dislikes
    phat = likes / n
    return (
        phat + z * z / (2 * n) - z * sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    ) / (1 + z * z / n)


with open("assets/openai_api_key.txt", "r") as f:
    os.environ["OPENAI_API_KEY"] = f.readline().strip()

gpt_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def send_message(text: str) -> str:
    try:
        response = gpt_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": text}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка: {e}"


async def tgdigest_impl(limit: int, offset_date: datetime, channels: list[Channel]):
    buffer = []
    async with aiosqlite.connect(DB_PATH) as db:
        for channel in channels:
            size = (
                await client(
                    functions.channels.GetFullChannelRequest(channel=channel.name)
                )
            ).full_chat.participants_count
            async for message in client.iter_messages(
                channel.name, limit, offset_date=offset_date, reverse=True
            ):
                link = f"https://t.me/{channel.name}/{message.id}"
                entity_id = await get_entity(db, link, True)
                score = get_popularity_score(message) / size + get_wilson_score(
                    await get_likes(db, entity_id),
                    await get_dislikes(db, entity_id),
                )
                buffer.append(
                    {
                        "score": score,
                        "text": message.message.strip().replace("\n", " "),
                        "entity_id": entity_id,
                        "link": link,
                        "description": message.message,
                    }
                )

    # Попытка сортировки через ChatGPT
    for attempt in range(3):
        try:
            posts = "\n".join([f"{i}: {item['text']}" for i, item in enumerate(buffer)])
            chatgpt_request = (
                f"У тебя есть {len(buffer)} постов, пронумерованных от 0 до {len(buffer) - 1}.\n\n"
                f"{posts}\n\n"
                "Упорядочь их по уровню интересности. Сначала самые интересные, затем менее. "
                "Ответ пришли в формате: 0,1,2,3,4..., то есть последовательность индексов постов через запятую"
            )

            response = send_message(chatgpt_request)

            sorted_indices = list(map(int, response.split(",")))
            sorted_buffer = [buffer[i] for i in sorted_indices]

            return [
                {"channel": item["channel"], "id": item["id"]}
                for item in sorted_buffer[:limit]
            ]

        except Exception as e:
            # Логируем если какая-то ошибка gpt
            print(f"Попытка {attempt + 1}: ошибка ChatGPT - {e}")

    # Если он с трех раз не смог, логируем это, и сортируем как было раньше
    print("ChatGPT не смог упорядочить посты. Используем базовую сортировку.")
    buffer.sort(key=lambda x: x["score"], reverse=True)
    result = buffer[:limit]
    async with aiosqlite.connect(DB_PATH) as db:
        for item in result:
            if item["entity_id"] == 0:
                item["entity_id"] = await get_entity(db, item["link"])
    return [
        {
            "link": item["link"],
            "entity_id": item["entity_id"],
            "description": item["description"],
        }
        for item in result
    ]


@app.get("/tgdigest")
async def tgdigest(request: TGDigestRequest):
    try:
        return await tgdigest_impl(request.limit, request.offset_date, request.channels)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class Feed(BaseModel):
    link: str


class RSSDigestRequest(BaseModel):
    user: str
    limit: int
    offset_date: datetime
    feeds: list[Feed]


async def rssdigest_impl(limit: int, offset_date: datetime, feeds: list[Feed]):
    buffer = []
    offset = offset_date.astimezone(pytz.UTC)
    for feed in feeds:
        data = feedparser.parse(feed.link)
        for entry in data.entries:
            if offset > datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z"):
                break
            buffer.append(
                {
                    "link": entry.link,
                    "description": entry.description,
                }
            )
    random.shuffle(buffer)  # simple ranking
    result = buffer[:limit]
    async with aiosqlite.connect(DB_PATH) as db:
        for item in result:
            item["entity_id"] = await get_entity(db, item["link"])
    return result


@app.get("/rssdigest")
async def rssdigest(request: RSSDigestRequest):
    try:
        return await rssdigest_impl(request.limit, request.offset_date, request.feeds)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class LikeRequest(BaseModel):
    user: str
    entity_id: int


@app.post("/like")
async def like(request: LikeRequest):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"INSERT OR IGNORE INTO likes VALUES({request.entity_id}, {await get_user(db, request.user)})"
            )
            await db.commit()
        return {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DislikeRequest(BaseModel):
    user: str
    entity_id: int


@app.post("/dislike")
async def dislike(request: DislikeRequest):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"INSERT OR IGNORE INTO dislikes VALUES({request.entity_id}, {await get_user(db, request.user)})"
            )
            await db.commit()
        return {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    config = uvicorn.Config(app=app)
    server = uvicorn.Server(config)
    loop.create_task(server.serve())
    loop.run_forever()
