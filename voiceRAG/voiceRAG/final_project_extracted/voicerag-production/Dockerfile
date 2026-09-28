FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY backend ./backend
COPY alembic.ini .
COPY alembic ./alembic
COPY .env.example ./.env.example
RUN mkdir -p /app/data /home/app/.cache && chown -R app:app /app /home/app
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
