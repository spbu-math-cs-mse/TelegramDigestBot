FROM python:3.13-slim

WORKDIR /recommendations

COPY code/recommendation-system/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY code/recommendation-system/main.py .

CMD ["python", "main.py"]