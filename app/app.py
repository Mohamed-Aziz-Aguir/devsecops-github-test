"""
Secure Task Manager API
Production-ready Flask application with basic security practices.
"""

import os
import uuid
import logging
from datetime import datetime

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, NotFound

# -------------------------------------------------
# Logging Configuration
# -------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Flask App Initialization
# -------------------------------------------------

app = Flask(__name__)

# -------------------------------------------------
# Security Headers Middleware
# -------------------------------------------------


@app.after_request
def set_security_headers(response):
    """Add security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


# -------------------------------------------------
# In-memory database
# -------------------------------------------------

tasks_db = {}


# -------------------------------------------------
# Task Model
# -------------------------------------------------


class Task:
    """Task model with validation."""

    def __init__(self, title, description="", priority="medium"):

        if not title or len(title) > 200:
            raise ValueError("Title must be between 1 and 200 characters")

        if len(description) > 1000:
            raise ValueError("Description must not exceed 1000 characters")

        if priority not in ["low", "medium", "high"]:
            raise ValueError("Priority must be low, medium, or high")

        self.id = str(uuid.uuid4())
        self.title = title
        self.description = description
        self.priority = priority
        self.created_at = datetime.utcnow().isoformat()
        self.completed = False

    def to_dict(self):
        """Convert task to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "created_at": self.created_at,
            "completed": self.completed,
        }


# -------------------------------------------------
# Health Check
# -------------------------------------------------


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "service": "secure-task-manager",
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


# -------------------------------------------------
# Get All Tasks
# -------------------------------------------------


@app.route("/tasks", methods=["GET"])
def get_tasks():
    """Retrieve all tasks."""

    completed = request.args.get("completed")

    task_list = [task.to_dict() for task in tasks_db.values()]

    if completed is not None:
        is_completed = completed.lower() == "true"
        task_list = [t for t in task_list if t["completed"] == is_completed]

    return jsonify({"tasks": task_list, "count": len(task_list)})


# -------------------------------------------------
# Create Task
# -------------------------------------------------


@app.route("/tasks", methods=["POST"])
def create_task():
    """Create a new task."""

    if not request.is_json:
        raise BadRequest("Content-Type must be application/json")

    data = request.get_json()

    if "title" not in data:
        raise BadRequest("Title is required")

    task = Task(
        title=data["title"],
        description=data.get("description", ""),
        priority=data.get("priority", "medium"),
    )

    tasks_db[task.id] = task

    logger.info("Created task %s", task.id)

    return jsonify(task.to_dict()), 201


# -------------------------------------------------
# Get Task by ID
# -------------------------------------------------


@app.route("/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    """Retrieve a task by ID."""

    task = tasks_db.get(task_id)

    if not task:
        raise NotFound("Task not found")

    return jsonify(task.to_dict())


# -------------------------------------------------
# Update Task
# -------------------------------------------------


@app.route("/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    """Update an existing task."""

    if not request.is_json:
        raise BadRequest("Content-Type must be application/json")

    task = tasks_db.get(task_id)

    if not task:
        raise NotFound("Task not found")

    data = request.get_json()

    if "title" in data:
        if not data["title"] or len(data["title"]) > 200:
            raise ValueError("Invalid title")
        task.title = data["title"]

    if "description" in data:
        if len(data["description"]) > 1000:
            raise ValueError("Description too long")
        task.description = data["description"]

    if "priority" in data:
        if data["priority"] not in ["low", "medium", "high"]:
            raise ValueError("Invalid priority")
        task.priority = data["priority"]

    if "completed" in data:
        task.completed = bool(data["completed"])

    logger.info("Updated task %s", task_id)

    return jsonify(task.to_dict())


# -------------------------------------------------
# Delete Task
# -------------------------------------------------


@app.route("/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """Delete a task."""

    task = tasks_db.pop(task_id, None)

    if not task:
        raise NotFound("Task not found")

    return jsonify(
        {
            "message": "Task deleted",
            "task": task.to_dict(),
        }
    )


# -------------------------------------------------
# Error Handlers
# -------------------------------------------------


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle server errors."""
    logger.error("Internal error: %s", error)
    return jsonify({"error": "Internal server error"}), 500


# -------------------------------------------------
# Run Application
# -------------------------------------------------

if __name__ == "__main__":

    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV") == "development"

    logger.info("Starting Secure Task Manager on port %s", port)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        threaded=True,
    )
