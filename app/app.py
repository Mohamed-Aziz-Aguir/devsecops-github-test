from flask import Flask, jsonify
import os

app = Flask(__name__)


@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "service": "devsecops-app"
    })


@app.route('/health')
def health():
    return jsonify({"status": "healthy"})


@app.route('/secure')
def secure():
    return jsonify({
        "security": "enabled",
        "message": "secure endpoint"
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Security fix: Use localhost by default, allow override via environment
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)
