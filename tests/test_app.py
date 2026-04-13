"""Unit tests for Flask application."""
import pytest
from app.app import app

@pytest.fixture
def client():
    """Test client fixture."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home(client):
    """Test home endpoint."""
    response = client.get('/')
    assert response.status_code == 200
    assert response.json['status'] == 'running'
    assert response.json['service'] == 'devsecops-app'

def test_health(client):
    """Test health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'healthy'

def test_secure(client):
    """Test secure endpoint."""
    response = client.get('/secure')
    assert response.status_code == 200
    assert response.json['security'] == 'enabled'
    assert response.json['message'] == 'secure endpoint'

def test_metrics(client):
    """Test metrics endpoint."""
    response = client.get('/metrics')
    assert response.status_code == 200
    assert 'uptime' in response.json
    assert response.json['status'] == 'operational'

def test_404(client):
    """Test 404 error handling."""
    response = client.get('/nonexistent')
    assert response.status_code == 404
    assert response.json['error'] == 'Not Found'
