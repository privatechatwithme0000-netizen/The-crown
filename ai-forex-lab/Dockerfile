FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps kept minimal; psycopg[binary] ships its own libpq.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY alembic ./alembic

RUN pip install --upgrade pip && pip install -e ".[dev]"

EXPOSE 8000

# Apply migrations then serve. Compose overrides command for other roles.
CMD ["sh", "-c", "alembic upgrade head && uvicorn forex_lab.main:app --host 0.0.0.0 --port 8000"]
