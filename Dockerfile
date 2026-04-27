# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

ARG APP_VERSION=0.1.0
ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIMESTAMP=${BUILD_TIMESTAMP}

WORKDIR /build

COPY pyproject.toml README.md /build/
COPY app /build/app

RUN python -m pip install --upgrade pip build && \
    python -m build --wheel --outdir /dist


FROM python:3.11-slim

ARG APP_VERSION=0.1.0
ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on \
    APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIMESTAMP=${BUILD_TIMESTAMP}

WORKDIR /app

RUN adduser --disabled-password --gecos "" --home /app appuser

COPY --from=builder /dist/*.whl /tmp/
RUN python -m pip install /tmp/*.whl && \
    rm -f /tmp/*.whl

RUN mkdir -p /app/scripts /app/artifacts && chown -R appuser:appuser /app

COPY --chown=appuser:appuser scripts/run_api.py /app/scripts/run_api.py

USER appuser

EXPOSE 8000

CMD ["python", "scripts/run_api.py"]
