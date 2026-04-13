import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home(client):
    """Test the home endpoint"""
    response = client.get('/')
    assert response.status_code == 200
    assert response.json['status'] == 'running'
    assert response.json['service'] == 'devsecops-app'

def test_health(client):
    """Test the health endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'healthy'

def test_secure(client):
    """Test the secure endpoint"""
    response = client.get('/secure')
    assert response.status_code == 200
    assert response.json['security'] == 'enabled'
    assert response.json['message'] == 'secure endpoint'

def test_404(client):
    """Test 404 for non-existent endpoint"""
    response = client.get('/nonexistent')
    assert response.status_code == 404
