FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=America/Mexico_City

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata gcc libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "psycopg[binary]>=3.2"

COPY src ./src
COPY scripts ./scripts
COPY sql ./sql
COPY data/signals ./data/signals

CMD ["python", "scripts/gcp_daily_job.py", "--mode", "ingest"]
