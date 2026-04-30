# Use Python 3.12 slim (actively maintained, fixes Python 3.11 weaknesses)
FROM python:3.12-slim

WORKDIR /app

# ============================================================================
# Fix ALL Debian system CVEs (glibc, tar, openssl, ca-certificates, etc.)
# ============================================================================
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ============================================================================
# Upgrade pip and wheel to fix Python‑tool CVEs
#   - pip: CVE-2025-8869, CVE-2026-3219, CVE-2026-1703
#   - wheel: CVE-2026-24049
# ============================================================================
RUN pip install --no-cache-dir --upgrade pip wheel

# Copy and install production dependencies (all Python CVEs already fixed)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

# Copy application code (assumes app.py is inside app/ directory)
COPY app/ app/

# Create non‑root user
RUN adduser --system --group appuser && \
    chown -R appuser:appuser /app

USER appuser

# Environment variables
ENV PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=5000 \
    WORKERS=4

EXPOSE 5000

# Health check (python3 is available in slim image)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Run with gunicorn (production)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--worker-class", "sync", "app.app:app"]
