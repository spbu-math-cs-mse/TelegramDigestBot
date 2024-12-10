import uvicorn
import asyncio
import aiosqlite
from telethon import TelegramClient, functions
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from contextlib import asynccontextmanager
from math import sqrt
import os
from openai import OpenAI

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
        CREATE INDEX IF NOT EXISTS likes_index
        ON likes(channel_id, message_id)
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
        await db.execute(
            """
        CREATE INDEX IF NOT EXISTS dislikes_index
        ON dislikes(channel_id, message_id)
        """
        )
        await db.commit()
    yield


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


async def get_likes(db: aiosqlite.Connection, channel_id: str, message_id: int) -> int:
    cursor = await db.execute(
        f"SELECT COUNT(*) FROM likes WHERE channel_id={await get_channel(db, channel_id)} AND message_id={message_id}"
    )
    row = await cursor.fetchone()
    return row[0]


async def get_dislikes(
    db: aiosqlite.Connection, channel_id: str, message_id: int
) -> int:
    cursor = await db.execute(
        f"SELECT COUNT(*) FROM dislikes WHERE channel_id={await get_channel(db, channel_id)} AND message_id={message_id}"
    )
    row = await cursor.fetchone()
    return row[0]


app = FastAPI(lifespan=lifespan)


class Channel(BaseModel):
    id: str


class DigestRequest(BaseModel):
    user_id: str
    limit: int
    offset_date: datetime
    channels: list[Channel]


def get_popularity_score(message) -> int:
    score = message.views
    if message.reactions is not None:
        score += len(message.reactions.results) * 5
    if message.replies is not None:
        score += message.replies.replies * 10
    return score


def get_wilson_score(likes, dislikes) -> float:
    if likes == 0:
        return -dislikes
    z = 1.64485
    n = likes + dislikes
    phat = likes / n
    return (
        phat + z * z / (2 * n) - z * sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    ) / (1 + z * z / n)

with open("openai_api_key.txt", "r") as f:
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

@app.get("/digest")
async def digest(request: DigestRequest):
    limit = request.limit
    offset_date = request.offset_date
    channels = request.channels
    buffer = []

    async with aiosqlite.connect(DB_PATH) as db:
        for channel in channels:
            size = (
                await client(
                    functions.channels.GetFullChannelRequest(channel=channel.id)
                )
            ).full_chat.participants_count
            async for message in client.iter_messages(
                channel.id, limit, offset_date=offset_date, reverse=True
            ):
                score = get_popularity_score(message) / size + get_wilson_score(
                    await get_likes(db, channel.id, message.id),
                    await get_dislikes(db, channel.id, message.id),
                )
                buffer.append(
                    {
                        "score": score,
                        "channel": channel.id,
                        "id": message.id,
                        "text": message.message.strip().replace("\n", " "),
                    }
                )

    # Попытка сортировки через ChatGPT
    for attempt in range(3):
        try:
            posts = "\n".join(
                [f"{i}: {item['text']}" for i, item in enumerate(buffer)]
            )
            chatgpt_request = (
                f"У тебя есть {len(buffer)} постов, пронумерованных от 0 до {len(buffer) - 1}.\n\n"
                f"{posts}\n\n"
                "Упорядочь их по уровню интересности. Сначала самые интересные, затем менее. "
                "Ответ пришли в формате: 0,1,2,3,4..., то есть последовательность индексов постов через запятую"
            )

            response = send_message(chatgpt_request)

            sorted_indices = list(map(int, response.split(",")))
            sorted_buffer = [buffer[i] for i in sorted_indices]

            return [{"channel": item["channel"], "id": item["id"]} for item in sorted_buffer[:limit]]

        except Exception as e:
            # Логируем если какая-то ошибка gpt
            print(f"Попытка {attempt + 1}: ошибка ChatGPT - {e}")

    # Если он с трех раз не смог, логируем это, и сортируем как было раньше
    print("ChatGPT не смог упорядочить посты. Используем базовую сортировку.")
    buffer.sort(key=lambda x: x["score"], reverse=True)
    return [{"channel": item["channel"], "id": item["id"]} for item in buffer[:limit]]

class LikeRequest(BaseModel):
    user_id: str
    channel: Channel
    id: int


@app.post("/like")
async def like(request: LikeRequest):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"INSERT OR IGNORE INTO likes VALUES({await get_channel(db, request.channel.id)}, {request.id}, {await get_user(db, request.user_id)})"
        )
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
