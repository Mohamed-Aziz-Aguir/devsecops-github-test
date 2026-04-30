# ---- Build Stage ----
FROM python:3.14-alpine AS builder

WORKDIR /app

# Temporarily add edge-main repository to get the latest patched packages
RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories

# Update system and install required build dependencies
RUN apk update && apk upgrade && \
    apk add --no-cache --virtual .build-deps \
        gcc g++ musl-dev make \
        file libffi-dev openssl-dev \
        libev-dev c-ares-dev \
        postgresql-dev

# Upgrade pip and prepare environment
RUN pip install --no-cache-dir --upgrade pip wheel

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# ---- Final Stage ----
FROM python:3.14-alpine

WORKDIR /app

# Copy only the installed Python packages from the builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

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
