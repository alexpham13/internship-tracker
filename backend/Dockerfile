# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN python -m pip install --no-cache-dir -r backend/requirements.txt \
    && groupadd --system interntrack \
    && useradd --system --gid interntrack interntrack

COPY alembic.ini ./
COPY backend/*.py backend/docker-entrypoint.sh backend/
COPY backend/alembic/env.py backend/alembic/script.py.mako backend/alembic/
COPY backend/alembic/versions/*.py backend/alembic/versions/

USER interntrack
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/app/backend/docker-entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
