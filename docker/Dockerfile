# Use Python 3.13 on Alpine 3.21 (latest stable)
FROM python:3.13-alpine3.21

WORKDIR /app

# Upgrade all Alpine system packages to latest available versions
RUN apk update && apk upgrade && rm -rf /var/cache/apk/*

# Install build dependencies (required for compiling some Python packages)
RUN apk add --no-cache \
    gcc g++ musl-dev make \
    file libffi-dev openssl-dev \
    libev-dev c-ares-dev \
    postgresql-dev

# Upgrade pip and wheel
RUN pip install --no-cache-dir --upgrade pip wheel

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# ============================================================================
# OPTIONAL: Remove build dependencies to reduce image size and CVEs
# Uncomment the following lines if you want to uninstall the build toolchain
# ============================================================================
# RUN apk del --no-cache gcc g++ musl-dev make file libffi-dev openssl-dev \
#     libev-dev c-ares-dev postgresql-dev && \
#     rm -rf /var/cache/apk/*

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
