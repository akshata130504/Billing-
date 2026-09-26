# syntax=docker/dockerfile:1.7
# Rooman Billing - API image.
#
# Build context is the REPOSITORY ROOT (not backend/), because the package is
# imported as `backend.app...` and alembic.ini uses script_location=backend/alembic
# with prepend_sys_path=. :
#
#   docker build -f backend/Dockerfile -t rooman-billing-api .
#
# The same image serves two roles (see docker-compose.prod.yml):
#   * backend   - gunicorn + uvicorn workers (default CMD). With WEB_CONCURRENCY>1
#                 SCHEDULER_ENABLED must be false, otherwise every worker would
#                 run the renewal/dunning jobs.
#   * scheduler - a single container with SCHEDULER_ENABLED=true running
#                 python -c "from backend.app.services.scheduler import run_forever; run_forever()"

# ---- Stage 1: build wheels ---------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY backend/requirements.txt ./requirements.txt
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---- Stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    BACKEND_PORT=8000 \
    WEB_CONCURRENCY=2 \
    RUN_MIGRATIONS=true \
    DB_WAIT_TIMEOUT=60

# Non-root runtime user with a fixed UID/GID.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

# Install the pre-built wheels (no compiler toolchain in the final image).
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl \
 && rm -rf /wheels

# Application code. backend/ lands in /app/backend so backend.app.main:app
# resolves with WORKDIR=/app. Only backend/requirements.txt is installed (no
# pytest/ruff - those are in requirements-dev.txt). The root .dockerignore keeps
# venvs, .env files, local databases, backend/tests and backend/uploads out of the
# context.
COPY --chown=app:app backend/ /app/backend/
COPY --chown=app:app pytest.ini /app/pytest.ini
COPY --chown=app:app backend/docker/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh \
 && chmod 0755 /app/entrypoint.sh \
 && find /app/backend -name '__pycache__' -type d -prune -exec rm -rf '{}' + \
 && rm -f /app/backend/.env

USER app

EXPOSE 8000

# python:slim has no curl; use the stdlib. /api/v1/health answers 200 even when the
# database is "degraded", so this only tells Docker the process is serving.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request; port=os.environ.get('BACKEND_PORT','8000'); r=urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % port, timeout=4); sys.exit(0 if r.status==200 else 1)"]

ENTRYPOINT ["/app/entrypoint.sh"]
# -w ${WEB_CONCURRENCY} is appended by the entrypoint so the value can come from the environment.
CMD ["gunicorn", "backend.app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "--timeout", "60", "--graceful-timeout", "30"]
