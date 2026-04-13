.PHONY: help setup test lint security docker clean

help:
	@echo "Available commands:"
	@echo "  make setup    - Setup virtual environment"
	@echo "  make test     - Run tests"
	@echo "  make lint     - Run linters"
	@echo "  make security - Run security scans"
	@echo "  make docker   - Build Docker image"
	@echo "  make clean    - Clean up artifacts"

setup:
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements-dev.txt

test:
	. venv/bin/activate && pytest tests/ -v --cov=app

lint:
	. venv/bin/activate && flake8 app/ --max-line-length=100
	. venv/bin/activate && pylint app/ --fail-under=6.0

security:
	. venv/bin/activate && bandit -r app/
	. venv/bin/activate && pip-audit

docker:
	docker build -t secure-task-app -f docker/Dockerfile .
	docker run -d -p 5000:5000 --name secure-task-app secure-task-app
	@sleep 3
	@curl -s http://localhost:5000/health | jq .
	@docker rm -f secure-task-app

clean:
	rm -rf venv/ __pycache__/ .pytest_cache/ .coverage htmlcov/
	rm -f bandit-report.json audit-report.json test-results.xml
	docker ps -q -f name=secure-task-app | grep -q . && docker rm -f secure-task-app || true
