FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-cloudrun.txt ./
RUN pip install --no-cache-dir -r requirements-cloudrun.txt

COPY . .

ENV OFP_DB_PATH=/tmp/oficina.db

CMD ["sh", "-c", "uvicorn servidor:app --host 0.0.0.0 --port ${PORT:-8080}"]
