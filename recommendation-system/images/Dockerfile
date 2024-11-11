FROM python:3.13-slim

WORKDIR /recommendation-system

COPY recommendation-system/dependencies/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY recommendation-system/source/main.py .
COPY recommendation-system/assets/credentials.txt .
COPY recommendation-system/assets/token.txt .

CMD ["python", "main.py"]