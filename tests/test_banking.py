import json
import pytest
from app.app import create_app, db as _db


@pytest.fixture
def app():
    """Create and configure a test app instance."""
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.drop_all()


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def auth_headers(client):
    """Register and login a user, return authorization headers."""
    # Register a user with a valid password (min 8 characters)
    register_resp = client.post('/auth/register', json={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'password123'   # length >= 8
    })
    assert register_resp.status_code == 201, f"Registration failed: {register_resp.data}"

    # Login
    login_resp = client.post('/auth/login', json={
        'username': 'testuser',
        'password': 'password123'
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.data}"
    token = login_resp.json['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_register(client):
    resp = client.post('/auth/register', json={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'secure123'
    })
    assert resp.status_code == 201
    data = resp.json
    assert 'access_token' in data
    assert data['user']['username'] == 'newuser'


def test_login(client):
    # Register first
    client.post('/auth/register', json={
        'username': 'loginuser',
        'email': 'login@example.com',
        'password': 'validpass123'
    })
    resp = client.post('/auth/login', json={
        'username': 'loginuser',
        'password': 'validpass123'
    })
    assert resp.status_code == 200
    assert 'access_token' in resp.json


def test_create_account(client, auth_headers):
    resp = client.post('/accounts', headers=auth_headers, json={
        'account_type': 'checking',
        'currency': 'USD'
    })
    assert resp.status_code == 201
    data = resp.json
    assert 'account' in data
    assert data['account']['account_type'] == 'checking'


def test_deposit(client, auth_headers):
    # Create an account first
    acc_resp = client.post('/accounts', headers=auth_headers, json={})
    assert acc_resp.status_code == 201
    account_id = acc_resp.json['account']['id']

    # Deposit money – API returns 201 Created
    resp = client.post('/transactions/deposit', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 100.00
    })
    assert resp.status_code == 201   # expecting 201, not 200
    tx_data = resp.json
    assert tx_data['transaction']['type'] == 'deposit'
    assert tx_data['account']['balance'] == 100.00


def test_withdraw(client, auth_headers):
    # Create account and deposit sufficient funds
    acc_resp = client.post('/accounts', headers=auth_headers, json={})
    account_id = acc_resp.json['account']['id']
    client.post('/transactions/deposit', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 200.00
    })

    # Withdraw – returns 201 Created
    resp = client.post('/transactions/withdraw', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 50.00
    })
    assert resp.status_code == 201
    data = resp.json
    assert data['transaction']['type'] == 'withdrawal'
    assert data['account']['balance'] == 150.00


def test_insufficient_funds(client, auth_headers):
    # Create account with no deposit
    acc_resp = client.post('/accounts', headers=auth_headers, json={})
    account_id = acc_resp.json['account']['id']

    # Attempt to withdraw more than balance – expect 400
    resp = client.post('/transactions/withdraw', headers=auth_headers, json={
        'account_id': account_id,
        'amount': 10.00
    })
    assert resp.status_code == 400
    assert 'Insufficient funds' in resp.json['error']
