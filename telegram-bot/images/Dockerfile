FROM python:3.13-slim

WORKDIR /bot

COPY telegram-bot/dependencies/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY telegram-bot/source/main.py .
COPY telegram-bot/assets/credentials.txt .
COPY telegram-bot/assets/token.txt .

CMD ["python", "main.py"]
