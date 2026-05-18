FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY yoyo ./yoyo

# Pre-download Maigret site DB so first request doesn't pay that cost
RUN maigret --self-check --no-progressbar dummy_seed_username 2>/dev/null || true

ENV PORT=8000 \
    YOYO_USE_FACE=1 \
    YOYO_USE_MAIGRET=1 \
    AWS_REGION=us-east-1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn yoyo.server:app --host 0.0.0.0 --port ${PORT}"]
