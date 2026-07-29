# ForestGuard — production image for Render / Docker hosts
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# OpenCV / ffmpeg (video keyframes + faststart)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY english_web ./english_web
COPY config ./config
COPY data/uploads/.gitkeep ./data/uploads/.gitkeep
COPY data/results/.gitkeep ./data/results/.gitkeep
COPY data/labels ./data/labels

# Sample library is large; omit from image (upload/analyze still works).
RUN mkdir -p data/samples

EXPOSE 8000

# Render injects $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
