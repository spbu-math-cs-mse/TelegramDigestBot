
FROM python:3.13-slim

WORKDIR /ds

COPY data-storage/dependencies/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY data-storage/source/main.py .

EXPOSE 5000

ENV FLASK_APP main.py
ENTRYPOINT ["python", "-m", "flask", "run", "--host=0.0.0.0"]