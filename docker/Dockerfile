FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .

# Install dependencies to a temporary location
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

# Create non-root user with proper home directory
RUN groupadd --system appgroup && \
    useradd --system --create-home --home-dir /home/appuser --shell /bin/bash \
    --no-log-init --gid appgroup appuser

# Copy installed packages from builder and fix permissions
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local

# Copy application files with proper ownership
COPY --chown=appuser:appgroup app/ app/
COPY --chown=appuser:appgroup tests/ tests/

# Add local Python binaries to PATH
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=5000

# Expose port
EXPOSE 5000

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app.app:app"]	
