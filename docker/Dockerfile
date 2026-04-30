FROM python:3.14-alpine

WORKDIR /app

# ============================================================================
# Upgrade all Alpine system packages (fixes Alpine CVEs)
# ============================================================================
RUN apk update && apk upgrade && rm -rf /var/cache/apk/*

# ============================================================================
# Upgrade pip and wheel to fix Python‑tool CVEs
# ============================================================================
RUN pip install --no-cache-dir --upgrade pip wheel

# Install system dependencies required for some Python packages (e.g., psycopg2)
# psycopg2-binary works on Alpine, but if you switch to psycopg2, uncomment:
# RUN apk add --no-cache postgresql-dev gcc musl-dev

# Copy and install production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# Copy application code
COPY app/ app/

# Create non‑root user (Alpine syntax)
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
