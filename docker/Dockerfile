FROM python:3.13-alpine

WORKDIR /app

# Upgrade Alpine system packages
RUN apk update && apk upgrade && rm -rf /var/cache/apk/*

# Install build dependencies for greenlet/gevent/psycopg2
RUN apk add --no-cache \
    gcc g++ musl-dev make \
    file libffi-dev openssl-dev \
    libev-dev c-ares-dev \
    postgresql-dev

# Upgrade pip and wheel
RUN pip install --no-cache-dir --upgrade pip wheel

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# Copy application code
COPY app/ app/

# Create non‑root user
RUN addgroup -g 1001 -S appuser && \
    adduser -S -u 1001 -G appuser appuser && \
    chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=5000 \
    WORKERS=4

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--worker-class", "sync", "app.app:app"]
