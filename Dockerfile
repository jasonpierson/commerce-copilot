# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on

WORKDIR /app

# System deps (optional, keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only project metadata first for layer caching
COPY pyproject.toml README.md /app/

# Install
RUN python -m pip install --upgrade pip && \
    pip install -e .

# Copy source
COPY app /app/app
COPY scripts /app/scripts
COPY docs /app/docs

EXPOSE 8000

# Use uvicorn directly so we can bind 0.0.0.0
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
