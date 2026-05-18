FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgl1 libglib2.0-0 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY yoyo ./yoyo

# Pre-download the InsightFace buffalo_l model and Maigret site DB so first request is fast
RUN python -c "from insightface.app import FaceAnalysis; a=FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']); a.prepare(ctx_id=-1, det_size=(640,640)); print('insightface ready')" \
 && maigret --self-check --no-progressbar dummy_seed_username 2>/dev/null || true

ENV PORT=8000 \
    YOYO_USE_FACE=1 \
    YOYO_USE_MAIGRET=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn yoyo.server:app --host 0.0.0.0 --port ${PORT}"]
