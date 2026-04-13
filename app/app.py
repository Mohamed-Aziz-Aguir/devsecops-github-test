"""
Flask application for DevSecOps testing.
Provides REST API endpoints for health checks and secure operations.
"""
import os
from flask import Flask, jsonify

app = Flask(__name__)


@app.route('/')
def home():
    """Return the service status."""
    return jsonify({
        "status": "running",
        "service": "devsecops-app"
    })


@app.route('/health')
def health():
    """Return the health status of the service."""
    return jsonify({"status": "healthy"})


@app.route('/secure')
def secure():
    """Return security status message."""
    return jsonify({
        "security": "enabled",
        "message": "secure endpoint"
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Security fix: Use localhost by default, allow override via environment
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)
