FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

# Create non-root user
RUN addgroup --system appgroup && \
    adduser --system --no-create-home --ingroup appgroup appuser

# Copy from builder
COPY --from=builder /root/.local /root/.local
COPY app/ app/
COPY tests/ tests/

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

# Security: Use localhost by default
ENV HOST=127.0.0.1
ENV PORT=5000

EXPOSE 5000

# Switch to non-root user
USER appuser

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app.app:app"]
