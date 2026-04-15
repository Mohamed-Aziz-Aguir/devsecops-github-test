"""
Production Flask application for DevSecOps pipeline.
Provides REST API endpoints with security headers and logging.
"""
import os
import time
import logging
from flask import Flask, jsonify, request, g


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# Security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


# Request timing middleware
@app.before_request
def before_request():
    """Start timer for request."""
    g.start_time = time.time()


@app.after_request
def after_request(response):
    """Log request duration."""
    if hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        logger.info("%s %s - %s - %.3fs", request.method, request.path, response.status_code, duration)
    return response


# Routes
@app.route('/')
def home():
    """Return service status."""
    return jsonify({
        "status": "running",
        "service": "devsecops-app"
    })


@app.route('/health')
def health():
    """Return health status."""
    return jsonify({"status": "healthy"})


@app.route('/secure')
def secure():
    """Return security status."""
    return jsonify({
        "security": "enabled",
        "message": "secure endpoint"
    })


@app.route('/metrics')
def metrics():
    """Return basic metrics."""
    return jsonify({
        "uptime": time.time() - app.config.get('START_TIME', time.time()),
        "status": "operational"
    })


# Error handlers
@app.errorhandler(404)
def not_found(error):  # pylint: disable=unused-argument
    """Handle 404 errors."""
    return jsonify({"error": "Not Found", "status": 404}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error("Internal server error: %s", error)
    return jsonify({"error": "Internal Server Error", "status": 500}), 500


# Initialize start time
app.config['START_TIME'] = time.time()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("ENVIRONMENT", "production") == "development"
    app.run(host=host, port=port, debug=debug)
