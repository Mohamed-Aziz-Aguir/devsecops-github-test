FROM python:3.11-slim

WORKDIR /app

# Install dependencies as root first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN groupadd --system appgroup && \
    useradd --system --create-home --home-dir /home/appuser \
    --shell /bin/bash --gid appgroup appuser

# Copy application files
COPY app/ app/
COPY tests/ tests/

# Fix permissions for the entire app directory
RUN chown -R appuser:appgroup /app && \
    chmod -R 755 /app

# Set environment variables
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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Run the application using python directly instead of gunicorn
CMD ["python", "-m", "app.app"]
