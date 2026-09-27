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
    && useradd --system --uid 10001 app \
    && mkdir /srv/data && chown app /srv/data

# The packages are installed into site-packages, so the pipeline cannot find config/ or a
# writable data/ relative to its source as it does in the editable dev venv.
ENV PPR_CONFIG_DIR=/srv/config \
    DATA_DIR=/srv/data

USER app
WORKDIR /srv/backend
EXPOSE 8000

# Behind a reverse proxy, set FORWARDED_ALLOW_IPS to the proxy's address (never "*" behind a
# proxy that appends to X-Forwarded-For), or every client shares the proxy's IP and its limits.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
