# tests/test_banking.py
import pytest
import json
from app.app import create_app, db as _db

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_headers(client):
    # Register and login to get tokens
    client.post('/auth/register', json={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'testpass123'
    })
    resp = client.post('/auth/login', json={
        'username': 'testuser',
        'password': 'testpass123'
    })
    tokens = json.loads(resp.data)
    return {'Authorization': f"Bearer {tokens['access_token']}"}

def test_register(client):
    resp = client.post('/auth/register', json={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'securepass123'
    })
    assert resp.status_code == 201
    assert 'access_token' in json.loads(resp.data)

def test_login(client):
    # First register
    client.post('/auth/register', json={
        'username': 'loginuser',
        'email': 'login@example.com',
        'password': 'pass123'
    })
    resp = client.post('/auth/login', json={
        'username': 'loginuser',
        'password': 'pass123'
    })
    assert resp.status_code == 200
    assert 'access_token' in json.loads(resp.data)

def test_create_account(client, auth_headers):
    resp = client.post('/accounts', headers=auth_headers, json={
        'account_type': 'checking'
    })
    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert 'account' in data
    assert data['account']['account_type'] == 'checking'

def test_deposit(client, auth_headers):
    # Create account first
    acc_resp = client.post('/accounts', headers=auth_headers, json={})
    account_id = json.loads(acc_resp.data)['account']['id']
    
    resp = client.post('/transactions/deposit', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 100.00
    })
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['new_balance'] == '100.00'

def test_withdraw(client, auth_headers):
    # Create account and deposit
    acc_resp = client.post('/accounts', headers=auth_headers, json={})
    account_id = json.loads(acc_resp.data)['account']['id']
    client.post('/transactions/deposit', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 200.00
    })
    
    resp = client.post('/transactions/withdraw', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 50.00
    })
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['new_balance'] == '150.00'

def test_insufficient_funds(client, auth_headers):
    acc_resp = client.post('/accounts', headers=auth_headers, json={})
    account_id = json.loads(acc_resp.data)['account']['id']
    
    resp = client.post('/transactions/withdraw', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 1000.00
    })
    assert resp.status_code == 400
    assert 'Insufficient funds' in json.loads(resp.data)['error']
