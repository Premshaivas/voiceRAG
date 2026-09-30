FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app
ARG TARGETARCH
RUN python -c "import os, urllib.request, zipfile; arch='aarch64' if os.environ.get('TARGETARCH')=='arm64' else 'x86_64'; url=f'https://github.com/denoland/deno/releases/download/v2.9.7/deno-{arch}-unknown-linux-gnu.zip'; path='/tmp/deno.zip'; urllib.request.urlretrieve(url, path); z=zipfile.ZipFile(path); z.extract('deno','/usr/local/bin'); os.chmod('/usr/local/bin/deno',0o755); os.remove(path)"
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch==2.5.1+cpu" \
    && pip install -r requirements.txt
COPY backend ./backend
COPY alembic.ini .
COPY alembic ./alembic
COPY .env.example ./.env.example
RUN mkdir -p /app/data /home/app/.cache && chown -R app:app /app /home/app
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
