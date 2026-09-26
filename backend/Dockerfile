# Used for the api, worker and scheduler services (different commands, same image).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY backend/pyproject.toml backend/
COPY backend/app backend/app
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/
COPY pipeline/pyproject.toml pipeline/
COPY pipeline/src pipeline/src
COPY config config

RUN pip install ./backend ./pipeline \
    && useradd --system --uid 10001 app

USER app
WORKDIR /srv/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
