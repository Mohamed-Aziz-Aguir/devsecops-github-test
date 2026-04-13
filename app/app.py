import os
from flask import Flask, jsonify, request

app = Flask(__name__)

tasks = []


@app.route("/")
def home():
    """Health check endpoint."""
    return jsonify({"message": "Secure Task Manager API"})


@app.route("/tasks", methods=["GET"])
def get_tasks():
    """Return all tasks."""
    return jsonify(tasks)


@app.route("/tasks", methods=["POST"])
def add_task():
    """Add a new task."""
    data = request.get_json()

    if not data or "task" not in data:
        return jsonify({"error": "Task content required"}), 400

    task = {
        "id": len(tasks) + 1,
        "task": data["task"],
        "done": False
    }

    tasks.append(task)

    return jsonify(task), 201


@app.route("/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    """Mark a task as completed."""
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            return jsonify(task)

    return jsonify({"error": "Task not found"}), 404


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    """Delete a task."""
    for task in tasks:
        if task["id"] == task_id:
            tasks.remove(task)
            return jsonify({"message": "Task deleted"})

    return jsonify({"error": "Task not found"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    host = os.environ.get("FLASK_HOST", "127.0.0.1")

    app.run(
        host=host,
        port=port,
        debug=False
    )
