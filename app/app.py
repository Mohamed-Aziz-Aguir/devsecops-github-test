"""
Secure Task Manager API
A production-grade Flask application with security best practices
"""

import os
import uuid
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, NotFound

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Security headers middleware
@app.after_request
def set_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response

# In-memory task storage (thread-safe for single process)
tasks_db = {}


class Task:
    """Task model with validation"""
    
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
        """Convert task to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'priority': self.priority,
            'created_at': self.created_at,
            'completed': self.completed
        }


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({
        'status': 'healthy',
        'service': 'secure-task-manager',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@app.route('/tasks', methods=['GET'])
def get_tasks():
    """Retrieve all tasks"""
    try:
        # Optional filtering by completion status
        completed = request.args.get('completed')
        
        task_list = [task.to_dict() for task in tasks_db.values()]
        
        if completed is not None:
            is_completed = completed.lower() == 'true'
            task_list = [t for t in task_list if t['completed'] == is_completed]
        
        logger.info(f"Retrieved {len(task_list)} tasks")
        
        return jsonify({
            'tasks': task_list,
            'count': len(task_list)
        }), 200
    
    except Exception as e:
        logger.error(f"Error retrieving tasks: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/tasks', methods=['POST'])
def create_task():
    """Create a new task"""
    try:
        if not request.is_json:
            raise BadRequest("Content-Type must be application/json")
        
        data = request.get_json()
        
        # Validate required fields
        if 'title' not in data:
            raise BadRequest("Title is required")
        
        # Create task with validation
        task = Task(
            title=data['title'],
            description=data.get('description', ''),
            priority=data.get('priority', 'medium')
        )
        
        # Store task
        tasks_db[task.id] = task
        
        logger.info(f"Created task: {task.id}")
        
        return jsonify(task.to_dict()), 201
    
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    
    except BadRequest as e:
        logger.warning(f"Bad request: {str(e)}")
        return jsonify({'error': str(e.description)}), 400
    
    except Exception as e:
        logger.error(f"Error creating task: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """Retrieve a specific task by ID"""
    try:
        if task_id not in tasks_db:
            raise NotFound("Task not found")
        
        task = tasks_db[task_id]
        logger.info(f"Retrieved task: {task_id}")
        
        return jsonify(task.to_dict()), 200
    
    except NotFound as e:
        logger.warning(f"Task not found: {task_id}")
        return jsonify({'error': str(e.description)}), 404
    
    except Exception as e:
        logger.error(f"Error retrieving task: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Delete a task by ID"""
    try:
        if task_id not in tasks_db:
            raise NotFound("Task not found")
        
        deleted_task = tasks_db.pop(task_id)
        logger.info(f"Deleted task: {task_id}")
        
        return jsonify({
            'message': 'Task deleted successfully',
            'task': deleted_task.to_dict()
        }), 200
    
    except NotFound as e:
        logger.warning(f"Task not found for deletion: {task_id}")
        return jsonify({'error': str(e.description)}), 404
    
    except Exception as e:
        logger.error(f"Error deleting task: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/tasks/<task_id>', methods=['PUT'])
def update_task(task_id):
    """Update a task by ID"""
    try:
        if task_id not in tasks_db:
            raise NotFound("Task not found")
        
        if not request.is_json:
            raise BadRequest("Content-Type must be application/json")
        
        data = request.get_json()
        task = tasks_db[task_id]
        
        # Update fields if provided
        if 'title' in data:
            if not data['title'] or len(data['title']) > 200:
                raise ValueError("Title must be between 1 and 200 characters")
            task.title = data['title']
        
        if 'description' in data:
            if len(data['description']) > 1000:
                raise ValueError("Description must not exceed 1000 characters")
            task.description = data['description']
        
        if 'priority' in data:
            if data['priority'] not in ["low", "medium", "high"]:
                raise ValueError("Priority must be low, medium, or high")
            task.priority = data['priority']
        
        if 'completed' in data:
            task.completed = bool(data['completed'])
        
        logger.info(f"Updated task: {task_id}")
        
        return jsonify(task.to_dict()), 200
    
    except NotFound as e:
        logger.warning(f"Task not found for update: {task_id}")
        return jsonify({'error': str(e.description)}), 404
    
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    
    except BadRequest as e:
        logger.warning(f"Bad request: {str(e)}")
        return jsonify({'error': str(e.description)}), 400
    
    except Exception as e:
        logger.error(f"Error updating task: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Resource not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Get configuration from environment variables
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    logger.info(f"Starting Secure Task Manager API on port {port}")
    
    # Run with production settings
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )
