FROM python:3.13-slim

WORKDIR /bot

COPY code/telegram-bot/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY code/telegram-bot/main.py .

CMD ["python", "main.py"]