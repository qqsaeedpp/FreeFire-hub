FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Tehran

WORKDIR /app

# System deps required to build asyncmy / cryptography
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev build-essential pkg-config tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Entry: run migrations then start the bot
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
