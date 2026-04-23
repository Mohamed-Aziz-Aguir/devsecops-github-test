# app/app.py
"""
Production banking backend with JWT authentication, PostgreSQL,
and core banking operations (deposit, withdraw, transfer).
Includes a full HTML/JS frontend served from Flask routes.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask, jsonify, request, g, Blueprint, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity
)
from flask_bcrypt import Bcrypt
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from marshmallow import Schema, fields, validate, ValidationError
from prometheus_flask_exporter import PrometheusMetrics

# ----------------------------------------------------------------------
# 1. App Configuration
# ----------------------------------------------------------------------

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-dev-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.environ.get('JWT_ACCESS_EXPIRES', 15)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get('JWT_REFRESH_EXPIRES', 7)))
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'postgresql://bankuser:bankpass@localhost:5432/bankdb'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    RATELIMIT_DEFAULT = "200 per day;50 per hour;5 per minute"
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True
    LOG_LEVEL = logging.INFO


class DevelopmentConfig(Config):
    DEBUG = True
    RATELIMIT_ENABLED = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=5)


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    RATELIMIT_ENABLED = True
    TALISMAN_FORCE_HTTPS = os.environ.get('FORCE_HTTPS', 'true').lower() == 'true'
    TALISMAN_STRICT_TRANSPORT_SECURITY = True
    TALISMAN_SESSION_COOKIE_SECURE = True


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# ----------------------------------------------------------------------
# 2. Extensions
# ----------------------------------------------------------------------

db = SQLAlchemy()
jwt = JWTManager()
bcrypt = Bcrypt()
limiter = Limiter(key_func=get_remote_address, storage_uri='memory://')

# ----------------------------------------------------------------------
# 3. HTML Template
# ----------------------------------------------------------------------

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SecureBank</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #f0f2f5; color: #1a1a2e; min-height: 100vh; }

  /* NAV */
  nav { background: #1a1a2e; color: #fff; padding: 0 2rem; display: flex; align-items: center;
        justify-content: space-between; height: 60px; box-shadow: 0 2px 8px rgba(0,0,0,.3); }
  nav .brand { font-size: 1.3rem; font-weight: 700; letter-spacing: 1px; color: #4fc3f7; }
  nav .nav-links { display: flex; gap: 1rem; align-items: center; }
  nav .nav-links span { color: #90caf9; font-size: .9rem; }
  nav button.nav-btn { background: transparent; border: 1px solid #4fc3f7; color: #4fc3f7;
      padding: .35rem .9rem; border-radius: 20px; cursor: pointer; font-size: .85rem;
      transition: all .2s; }
  nav button.nav-btn:hover { background: #4fc3f7; color: #1a1a2e; }

  /* PAGES */
  .page { display: none; padding: 2rem; max-width: 1100px; margin: 0 auto; }
  .page.active { display: block; }

  /* AUTH CARD */
  .auth-wrap { display: flex; justify-content: center; align-items: center; min-height: calc(100vh - 60px); }
  .auth-card { background: #fff; border-radius: 12px; padding: 2.5rem; width: 100%; max-width: 420px;
               box-shadow: 0 4px 24px rgba(0,0,0,.1); }
  .auth-card h2 { margin-bottom: 1.5rem; color: #1a1a2e; font-size: 1.5rem; }
  .auth-card p { font-size: .9rem; color: #666; margin-top: 1rem; text-align: center; }
  .auth-card a { color: #1565c0; cursor: pointer; text-decoration: underline; }

  /* FORMS */
  .form-group { margin-bottom: 1rem; }
  .form-group label { display: block; font-size: .85rem; font-weight: 600; margin-bottom: .4rem; color: #444; }
  .form-group input, .form-group select {
      width: 100%; padding: .65rem .9rem; border: 1px solid #ddd; border-radius: 8px;
      font-size: .95rem; transition: border .2s; outline: none; }
  .form-group input:focus, .form-group select:focus { border-color: #1565c0; }

  /* BUTTONS */
  .btn { padding: .65rem 1.4rem; border: none; border-radius: 8px; cursor: pointer;
         font-size: .95rem; font-weight: 600; transition: all .2s; }
  .btn-primary { background: #1565c0; color: #fff; width: 100%; margin-top: .5rem; }
  .btn-primary:hover { background: #0d47a1; }
  .btn-success { background: #2e7d32; color: #fff; }
  .btn-success:hover { background: #1b5e20; }
  .btn-warning { background: #e65100; color: #fff; }
  .btn-warning:hover { background: #bf360c; }
  .btn-info { background: #01579b; color: #fff; }
  .btn-info:hover { background: #003c6e; }
  .btn-sm { padding: .4rem .9rem; font-size: .85rem; border-radius: 6px; }

  /* ALERTS */
  .alert { padding: .75rem 1rem; border-radius: 8px; margin-bottom: 1rem; font-size: .9rem; display: none; }
  .alert.show { display: block; }
  .alert-error { background: #ffebee; color: #c62828; border: 1px solid #ef9a9a; }
  .alert-success { background: #e8f5e9; color: #1b5e20; border: 1px solid #a5d6a7; }

  /* DASHBOARD GRID */
  .dashboard-header { margin-bottom: 2rem; }
  .dashboard-header h1 { font-size: 1.8rem; color: #1a1a2e; }
  .dashboard-header p { color: #666; margin-top: .3rem; }

  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.2rem; margin-bottom: 2rem; }
  .stat-card { background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,.07); }
  .stat-card .label { font-size: .8rem; color: #888; text-transform: uppercase; letter-spacing: .5px; }
  .stat-card .value { font-size: 1.8rem; font-weight: 700; color: #1a1a2e; margin-top: .3rem; }
  .stat-card .sub { font-size: .8rem; color: #aaa; margin-top: .2rem; }

  /* PANELS */
  .panel-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }
  @media (max-width: 700px) { .panel-grid { grid-template-columns: 1fr; } }
  .panel { background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,.07); }
  .panel h3 { font-size: 1rem; font-weight: 700; margin-bottom: 1.2rem; color: #1a1a2e;
              padding-bottom: .6rem; border-bottom: 2px solid #e3f2fd; }

  /* ACCOUNTS */
  .account-list { display: flex; flex-direction: column; gap: .8rem; }
  .account-item { background: linear-gradient(135deg, #1565c0, #0d47a1); color: #fff;
                  border-radius: 10px; padding: 1rem 1.2rem; display: flex;
                  justify-content: space-between; align-items: center; }
  .account-item .acc-info .acc-num { font-size: .8rem; opacity: .8; }
  .account-item .acc-info .acc-type { font-size .85rem; text-transform: capitalize; opacity: .9; }
  .account-item .acc-balance { font-size: 1.3rem; font-weight: 700; }
  .account-item .acc-currency { font-size: .75rem; opacity: .8; }

  /* TABS */
  .tabs { display: flex; gap: .5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .tab-btn { padding: .5rem 1.2rem; border: 2px solid #e0e0e0; border-radius: 20px;
             background: #fff; cursor: pointer; font-size: .85rem; font-weight: 600;
             color: #666; transition: all .2s; }
  .tab-btn.active { border-color: #1565c0; background: #1565c0; color: #fff; }

  /* TABLE */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  th { background: #f5f5f5; padding: .7rem 1rem; text-align: left; font-size: .8rem;
       text-transform: uppercase; letter-spacing: .5px; color: #666; }
  td { padding: .7rem 1rem; border-bottom: 1px solid #f0f0f0; }
  tr:last-child td { border-bottom: none; }
  .badge { display: inline-block; padding: .2rem .6rem; border-radius: 12px; font-size: .75rem; font-weight: 600; }
  .badge-deposit { background: #e8f5e9; color: #2e7d32; }
  .badge-withdrawal { background: #fff3e0; color: #e65100; }
  .badge-transfer { background: #e3f2fd; color: #1565c0; }
  .badge-completed { background: #e8f5e9; color: #2e7d32; }
  .badge-pending { background: #fff9c4; color: #f57f17; }

  /* MODAL */
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5);
                   z-index: 1000; justify-content: center; align-items: center; }
  .modal-overlay.open { display: flex; }
  .modal { background: #fff; border-radius: 12px; padding: 2rem; width: 100%; max-width: 420px;
           box-shadow: 0 8px 32px rgba(0,0,0,.2); }
  .modal h3 { margin-bottom: 1.2rem; font-size: 1.1rem; }
  .modal-actions { display: flex; gap: .8rem; margin-top: 1rem; }
  .btn-cancel { background: #f5f5f5; color: #333; }
  .btn-cancel:hover { background: #e0e0e0; }

  /* LOADER */
  .spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid rgba(255,255,255,.4);
             border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .empty-state { text-align: center; padding: 2rem; color: #aaa; font-size: .9rem; }
</style>
</head>
<body>

<!-- NAV -->
<nav>
  <div class="brand">&#9632; SecureBank</div>
  <div class="nav-links">
    <span id="nav-username"></span>
    <button class="nav-btn" id="btn-new-account" onclick="openNewAccountModal()" style="display:none">+ Account</button>
    <button class="nav-btn" id="btn-logout" onclick="logout()" style="display:none">Logout</button>
  </div>
</nav>

<!-- AUTH PAGE -->
<div id="page-auth" class="page active">
  <div class="auth-wrap">
    <div class="auth-card">
      <div id="auth-alert" class="alert"></div>

      <!-- LOGIN -->
      <div id="form-login">
        <h2>Welcome back</h2>
        <div class="form-group" style="margin-top:1.2rem">
          <label>Username</label>
          <input type="text" id="login-username" placeholder="Enter username" />
        </div>
        <div class="form-group">
          <label>Password</label>
          <input type="password" id="login-password" placeholder="Enter password" />
        </div>
        <button class="btn btn-primary" onclick="login()">Sign In</button>
        <p>No account? <a onclick="showRegister()">Create one</a></p>
      </div>

      <!-- REGISTER -->
      <div id="form-register" style="display:none">
        <h2>Create account</h2>
        <div class="form-group" style="margin-top:1.2rem">
          <label>Username</label>
          <input type="text" id="reg-username" placeholder="Choose a username" />
        </div>
        <div class="form-group">
          <label>Email</label>
          <input type="email" id="reg-email" placeholder="your@email.com" />
        </div>
        <div class="form-group">
          <label>Password</label>
          <input type="password" id="reg-password" placeholder="Min 6 characters" />
        </div>
        <button class="btn btn-primary" onclick="register()">Create Account</button>
        <p>Already have one? <a onclick="showLogin()">Sign in</a></p>
      </div>
    </div>
  </div>
</div>

<!-- DASHBOARD PAGE -->
<div id="page-dashboard" class="page">

  <div class="dashboard-header">
    <h1>Dashboard</h1>
    <p id="dash-subtitle">Overview of your accounts</p>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="label">Total Balance</div>
      <div class="value" id="stat-total">$0.00</div>
      <div class="sub">Across all accounts</div>
    </div>
    <div class="stat-card">
      <div class="label">Accounts</div>
      <div class="value" id="stat-accounts">0</div>
      <div class="sub">Active accounts</div>
    </div>
    <div class="stat-card">
      <div class="label">Transactions</div>
      <div class="value" id="stat-txns">0</div>
      <div class="sub">Total recorded</div>
    </div>
  </div>

  <div class="panel-grid">
    <!-- Accounts -->
    <div class="panel">
      <h3>My Accounts</h3>
      <div class="account-list" id="account-list">
        <div class="empty-state">No accounts yet</div>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="panel">
      <h3>Quick Actions</h3>
      <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('deposit')">Deposit</button>
        <button class="tab-btn" onclick="switchTab('withdraw')">Withdraw</button>
        <button class="tab-btn" onclick="switchTab('transfer')">Transfer</button>
      </div>

      <div id="action-alert" class="alert"></div>

      <!-- Deposit -->
      <div id="tab-deposit">
        <div class="form-group">
          <label>Account</label>
          <select id="dep-account"></select>
        </div>
        <div class="form-group">
          <label>Amount (USD)</label>
          <input type="number" id="dep-amount" placeholder="0.00" min="0.01" step="0.01" />
        </div>
        <button class="btn btn-success btn-sm" onclick="doDeposit()">Deposit Funds</button>
      </div>

      <!-- Withdraw -->
      <div id="tab-withdraw" style="display:none">
        <div class="form-group">
          <label>Account</label>
          <select id="with-account"></select>
        </div>
        <div class="form-group">
          <label>Amount (USD)</label>
          <input type="number" id="with-amount" placeholder="0.00" min="0.01" step="0.01" />
        </div>
        <button class="btn btn-warning btn-sm" onclick="doWithdraw()">Withdraw Funds</button>
      </div>

      <!-- Transfer -->
      <div id="tab-transfer" style="display:none">
        <div class="form-group">
          <label>From Account</label>
          <select id="trf-from"></select>
        </div>
        <div class="form-group">
          <label>To Account ID</label>
          <input type="number" id="trf-to" placeholder="Destination account ID" />
        </div>
        <div class="form-group">
          <label>Amount (USD)</label>
          <input type="number" id="trf-amount" placeholder="0.00" min="0.01" step="0.01" />
        </div>
        <div class="form-group">
          <label>Description (optional)</label>
          <input type="text" id="trf-desc" placeholder="Payment for..." />
        </div>
        <button class="btn btn-info btn-sm" onclick="doTransfer()">Send Transfer</button>
      </div>
    </div>
  </div>

  <!-- Transaction History -->
  <div class="panel">
    <h3>Transaction History</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Reference</th>
            <th>Type</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody id="txn-table-body">
          <tr><td colspan="5" class="empty-state">No transactions yet</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<!-- NEW ACCOUNT MODAL -->
<div class="modal-overlay" id="modal-new-account">
  <div class="modal">
    <h3>Open New Account</h3>
    <div id="modal-alert" class="alert"></div>
    <div class="form-group">
      <label>Account Type</label>
      <select id="new-acc-type">
        <option value="checking">Checking</option>
        <option value="savings">Savings</option>
      </select>
    </div>
    <div class="form-group">
      <label>Currency</label>
      <select id="new-acc-currency">
        <option value="USD">USD</option>
        <option value="EUR">EUR</option>
        <option value="GBP">GBP</option>
      </select>
    </div>
    <div class="modal-actions">
      <button class="btn btn-primary" onclick="createAccount()">Open Account</button>
      <button class="btn btn-cancel" onclick="closeNewAccountModal()">Cancel</button>
    </div>
  </div>
</div>

<script>
// ----------------------------------------------------------------
// State
// ----------------------------------------------------------------
let token = localStorage.getItem('token') || null;
let currentUser = null;
let accounts = [];

// ----------------------------------------------------------------
// Boot
// ----------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  if (token) loadDashboard();
});

// ----------------------------------------------------------------
// Page routing
// ----------------------------------------------------------------
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
}

function showRegister() {
  document.getElementById('form-login').style.display = 'none';
  document.getElementById('form-register').style.display = 'block';
  clearAuthAlert();
}

function showLogin() {
  document.getElementById('form-register').style.display = 'none';
  document.getElementById('form-login').style.display = 'block';
  clearAuthAlert();
}

// ----------------------------------------------------------------
// Alerts
// ----------------------------------------------------------------
function showAlert(id, msg, type) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.className = 'alert show alert-' + type;
}

function hideAlert(id) {
  document.getElementById(id).className = 'alert';
}

function clearAuthAlert() { hideAlert('auth-alert'); }

// ----------------------------------------------------------------
// API helper
// ----------------------------------------------------------------
async function api(method, path, body, auth) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth && token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

// ----------------------------------------------------------------
// Auth
// ----------------------------------------------------------------
async function login() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  if (!username || !password) return showAlert('auth-alert', 'Fill in all fields.', 'error');

  const { ok, data } = await api('POST', '/auth/login', { username, password });
  if (!ok) return showAlert('auth-alert', data.error || 'Login failed.', 'error');

  token = data.access_token;
  localStorage.setItem('token', token);
  currentUser = data.user;
  loadDashboard();
}

async function register() {
  const username = document.getElementById('reg-username').value.trim();
  const email = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  if (!username || !email || !password) return showAlert('auth-alert', 'Fill in all fields.', 'error');

  const { ok, data } = await api('POST', '/auth/register', { username, email, password });
  if (!ok) return showAlert('auth-alert', data.error || 'Registration failed.', 'error');

  token = data.access_token;
  localStorage.setItem('token', token);
  currentUser = data.user;
  loadDashboard();
}

function logout() {
  token = null;
  currentUser = null;
  accounts = [];
  localStorage.removeItem('token');
  document.getElementById('nav-username').textContent = '';
  document.getElementById('btn-logout').style.display = 'none';
  document.getElementById('btn-new-account').style.display = 'none';
  showLogin();
  showPage('auth');
}

// ----------------------------------------------------------------
// Dashboard
// ----------------------------------------------------------------
async function loadDashboard() {
  showPage('dashboard');
  document.getElementById('btn-logout').style.display = 'inline-block';
  document.getElementById('btn-new-account').style.display = 'inline-block';

  await loadAccounts();
  await loadTransactions();
}

async function loadAccounts() {
  const { ok, data } = await api('GET', '/accounts', null, true);
  if (!ok) { if (data.status === 401) return logout(); return; }

  accounts = data.accounts;
  document.getElementById('stat-accounts').textContent = accounts.length;

  const total = accounts.reduce((s, a) => s + parseFloat(a.balance), 0);
  document.getElementById('stat-total').textContent = '$' + total.toFixed(2);

  if (currentUser) {
    document.getElementById('nav-username').textContent = currentUser.username;
    document.getElementById('dash-subtitle').textContent =
      'Welcome back, ' + currentUser.username;
  }

  // Render account cards
  const list = document.getElementById('account-list');
  if (accounts.length === 0) {
    list.innerHTML = '<div class="empty-state">No accounts — click "+ Account" to open one</div>';
  } else {
    list.innerHTML = accounts.map(a => `
      <div class="account-item">
        <div class="acc-info">
          <div class="acc-num">${a.account_number}</div>
          <div class="acc-type">${a.account_type}</div>
        </div>
        <div style="text-align:right">
          <div class="acc-balance">$${parseFloat(a.balance).toFixed(2)}</div>
          <div class="acc-currency">${a.currency}</div>
        </div>
      </div>
    `).join('');
  }

  // Populate selects
  const opts = accounts.map(a =>
    `<option value="${a.id}">${a.account_number} ($${parseFloat(a.balance).toFixed(2)})</option>`
  ).join('');
  ['dep-account','with-account','trf-from'].forEach(id => {
    document.getElementById(id).innerHTML = opts || '<option>No accounts</option>';
  });
}

async function loadTransactions() {
  const { ok, data } = await api('GET', '/transactions/history', null, true);
  if (!ok) return;

  document.getElementById('stat-txns').textContent = data.count;

  const tbody = document.getElementById('txn-table-body');
  if (data.count === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No transactions yet</td></tr>';
    return;
  }

  tbody.innerHTML = data.transactions.map(t => `
    <tr>
      <td style="font-family:monospace;font-size:.8rem">${t.reference || '-'}</td>
      <td><span class="badge badge-${t.type}">${t.type}</span></td>
      <td><strong>$${parseFloat(t.amount).toFixed(2)}</strong></td>
      <td><span class="badge badge-${t.status}">${t.status}</span></td>
      <td style="color:#888;font-size:.85rem">${new Date(t.created_at).toLocaleString()}</td>
    </tr>
  `).join('');
}

// ----------------------------------------------------------------
// Tabs
// ----------------------------------------------------------------
function switchTab(name) {
  ['deposit','withdraw','transfer'].forEach(t => {
    document.getElementById('tab-' + t).style.display = t === name ? 'block' : 'none';
    document.querySelectorAll('.tab-btn').forEach((btn, i) => {
      btn.classList.toggle('active', ['deposit','withdraw','transfer'][i] === name);
    });
  });
  hideAlert('action-alert');
}

// ----------------------------------------------------------------
// Transactions
// ----------------------------------------------------------------
async function doDeposit() {
  const account_id = parseInt(document.getElementById('dep-account').value);
  const amount = parseFloat(document.getElementById('dep-amount').value);
  if (!amount || amount <= 0) return showAlert('action-alert', 'Enter a valid amount.', 'error');

  const { ok, data } = await api('POST', '/transactions/deposit', { account_id, amount }, true);
  if (!ok) return showAlert('action-alert', data.error || 'Deposit failed.', 'error');

  showAlert('action-alert', `Deposit successful! New balance: $${parseFloat(data.new_balance).toFixed(2)}`, 'success');
  document.getElementById('dep-amount').value = '';
  await loadAccounts();
  await loadTransactions();
}

async function doWithdraw() {
  const account_id = parseInt(document.getElementById('with-account').value);
  const amount = parseFloat(document.getElementById('with-amount').value);
  if (!amount || amount <= 0) return showAlert('action-alert', 'Enter a valid amount.', 'error');

  const { ok, data } = await api('POST', '/transactions/withdraw', { account_id, amount }, true);
  if (!ok) return showAlert('action-alert', data.error || 'Withdrawal failed.', 'error');

  showAlert('action-alert', `Withdrawal successful! New balance: $${parseFloat(data.new_balance).toFixed(2)}`, 'success');
  document.getElementById('with-amount').value = '';
  await loadAccounts();
  await loadTransactions();
}

async function doTransfer() {
  const from_account_id = parseInt(document.getElementById('trf-from').value);
  const to_account_id = parseInt(document.getElementById('trf-to').value);
  const amount = parseFloat(document.getElementById('trf-amount').value);
  const description = document.getElementById('trf-desc').value;

  if (!to_account_id || !amount || amount <= 0)
    return showAlert('action-alert', 'Fill in all transfer fields.', 'error');

  const { ok, data } = await api('POST', '/transactions/transfer',
    { from_account_id, to_account_id, amount, description }, true);
  if (!ok) return showAlert('action-alert', data.error || 'Transfer failed.', 'error');

  showAlert('action-alert', `Transfer successful! Your balance: $${parseFloat(data.source_balance).toFixed(2)}`, 'success');
  document.getElementById('trf-to').value = '';
  document.getElementById('trf-amount').value = '';
  document.getElementById('trf-desc').value = '';
  await loadAccounts();
  await loadTransactions();
}

// ----------------------------------------------------------------
// New Account Modal
// ----------------------------------------------------------------
function openNewAccountModal() {
  document.getElementById('modal-new-account').classList.add('open');
  hideAlert('modal-alert');
}

function closeNewAccountModal() {
  document.getElementById('modal-new-account').classList.remove('open');
}

async function createAccount() {
  const account_type = document.getElementById('new-acc-type').value;
  const currency = document.getElementById('new-acc-currency').value;

  const { ok, data } = await api('POST', '/accounts', { account_type, currency }, true);
  if (!ok) return showAlert('modal-alert', data.error || 'Failed to create account.', 'error');

  closeNewAccountModal();
  await loadAccounts();
}

// Close modal on overlay click
document.getElementById('modal-new-account').addEventListener('click', function(e) {
  if (e.target === this) closeNewAccountModal();
});

// Enter key support
document.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    if (document.getElementById('form-login').style.display !== 'none') login();
    else if (document.getElementById('form-register').style.display !== 'none') register();
  }
});
</script>
</body>
</html>
"""

# ----------------------------------------------------------------------
# 4. App Factory
# ----------------------------------------------------------------------

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    app = Flask(__name__)
    app.config.from_object(config.get(config_name, DevelopmentConfig))

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)

    PrometheusMetrics(app, group_by='endpoint')

    Talisman(
        app,
        force_https=app.config.get('TALISMAN_FORCE_HTTPS', False),
        strict_transport_security=app.config.get('TALISMAN_STRICT_TRANSPORT_SECURITY', True),
        session_cookie_secure=app.config.get('TALISMAN_SESSION_COOKIE_SECURE', True),
        content_security_policy={
            'default-src': "'self'",
            'script-src': ["'self'", "'unsafe-inline'"],
            'style-src': ["'self'", "'unsafe-inline'"],
        }
    )

    @app.before_request
    def start_timer():
        g.start_time = time.time()

    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            app.logger.info('%s %s - %s (%.3fs)',
                request.method, request.path, response.status_code, duration)
        return response

    @app.route('/health')
    def health():
        return jsonify({"status": "healthy"})

    @app.route('/')
    def home():
        return render_template_string(HTML)

    @app.route('/secure')
    def secure():
        return jsonify({"security": "enabled", "message": "secure endpoint"})

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(transactions_bp, url_prefix='/transactions')

    app.config['START_TIME'] = time.time()
    return app

# ----------------------------------------------------------------------
# 5. Models
# ----------------------------------------------------------------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    accounts = db.relationship('Account', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat(),
            'is_active': self.is_active
        }


class Account(db.Model):
    __tablename__ = 'accounts'
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    account_type = db.Column(db.String(20), nullable=False, default='checking')
    balance = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    outgoing_transactions = db.relationship(
        'Transaction', foreign_keys='Transaction.from_account_id', backref='source')
    incoming_transactions = db.relationship(
        'Transaction', foreign_keys='Transaction.to_account_id', backref='destination')

    def to_dict(self):
        return {
            'id': self.id,
            'account_number': self.account_number,
            'account_type': self.account_type,
            'balance': str(self.balance),
            'currency': self.currency,
            'created_at': self.created_at.isoformat()
        }


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    description = db.Column(db.String(200))
    reference = db.Column(db.String(50), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    from_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    to_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))

    def to_dict(self):
        return {
            'id': self.id,
            'amount': str(self.amount),
            'type': self.type,
            'status': self.status,
            'description': self.description,
            'reference': self.reference,
            'created_at': self.created_at.isoformat(),
            'from_account': self.from_account_id,
            'to_account': self.to_account_id
        }

# ----------------------------------------------------------------------
# 6. Schemas
# ----------------------------------------------------------------------

class RegisterSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=3, max=80))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=6))

class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True)

class CreateAccountSchema(Schema):
    account_type = fields.Str(
        validate=validate.OneOf(['checking', 'savings']), load_default='checking')
    currency = fields.Str(
        validate=validate.Regexp(r'^[A-Z]{3}$'), load_default='USD')

class DepositSchema(Schema):
    account_id = fields.Int(required=True)
    amount = fields.Decimal(required=True,
        validate=validate.Range(min=Decimal('0.01'), max=Decimal('100000')))

class WithdrawSchema(Schema):
    account_id = fields.Int(required=True)
    amount = fields.Decimal(required=True,
        validate=validate.Range(min=Decimal('0.01'), max=Decimal('50000')))

class TransferSchema(Schema):
    from_account_id = fields.Int(required=True)
    to_account_id = fields.Int(required=True)
    amount = fields.Decimal(required=True,
        validate=validate.Range(min=Decimal('0.01'), max=Decimal('50000')))
    description = fields.Str(validate=validate.Length(max=200), load_default='')

# ----------------------------------------------------------------------
# 7. Helpers
# ----------------------------------------------------------------------

def generate_account_number():
    import random, string
    while True:
        num = 'BANK-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not Account.query.filter_by(account_number=num).first():
            return num

def generate_transaction_reference():
    import random, string
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'TXN-{ts}-{rnd}'

def handle_validation_error(error):
    return jsonify({'error': 'Validation Error', 'message': error.messages, 'status': 400}), 400

# ----------------------------------------------------------------------
# 8. JWT Callbacks
# ----------------------------------------------------------------------

@jwt.user_identity_loader
def user_identity_lookup(user):
    return user.id

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    return db.session.get(User, jwt_data["sub"])

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    return False

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({'error': 'Token Expired', 'status': 401}), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({'error': 'Invalid Token', 'message': str(error), 'status': 422}), 422

@jwt.unauthorized_loader
def unauthorized_callback(error):
    return jsonify({'error': 'Unauthorized', 'status': 401}), 401

# ----------------------------------------------------------------------
# 9. Blueprints
# ----------------------------------------------------------------------

auth_bp = Blueprint('auth', __name__)
accounts_bp = Blueprint('accounts', __name__)
transactions_bp = Blueprint('transactions', __name__)

@auth_bp.route('/register', methods=['POST'])
@limiter.limit('5 per hour')
def register():
    data = request.get_json()
    try:
        validated = RegisterSchema().load(data)
    except ValidationError as err:
        return handle_validation_error(err)
    if User.query.filter_by(username=validated['username']).first():
        return jsonify({'error': 'Username already exists', 'status': 409}), 409
    if User.query.filter_by(email=validated['email']).first():
        return jsonify({'error': 'Email already registered', 'status': 409}), 409
    user = User(username=validated['username'], email=validated['email'])
    user.set_password(validated['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({
        'message': 'User created successfully',
        'access_token': create_access_token(identity=user),
        'refresh_token': create_refresh_token(identity=user),
        'user': user.to_dict()
    }), 201

@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = request.get_json()
    try:
        validated = LoginSchema().load(data)
    except ValidationError as err:
        return handle_validation_error(err)
    user = User.query.filter_by(username=validated['username']).first()
    if not user or not user.check_password(validated['password']):
        return jsonify({'error': 'Invalid credentials', 'status': 401}), 401
    return jsonify({
        'access_token': create_access_token(identity=user),
        'refresh_token': create_refresh_token(identity=user),
        'user': user.to_dict()
    }), 200

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    return jsonify({'access_token': create_access_token(identity=get_jwt_identity())}), 200

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    return jsonify({'message': 'Successfully logged out'}), 200

@accounts_bp.route('', methods=['GET'])
@jwt_required()
def get_accounts():
    accounts = Account.query.filter_by(user_id=get_jwt_identity()).all()
    return jsonify({'accounts': [a.to_dict() for a in accounts]}), 200

@accounts_bp.route('/<int:account_id>/balance', methods=['GET'])
@jwt_required()
def get_balance(account_id):
    account = Account.query.filter_by(id=account_id, user_id=get_jwt_identity()).first()
    if not account:
        return jsonify({'error': 'Account not found', 'status': 404}), 404
    return jsonify({
        'account_number': account.account_number,
        'balance': str(account.balance),
        'currency': account.currency
    }), 200

@accounts_bp.route('', methods=['POST'])
@jwt_required()
def create_account():
    data = request.get_json() or {}
    try:
        validated = CreateAccountSchema().load(data)
    except ValidationError as err:
        return handle_validation_error(err)
    account = Account(
        account_number=generate_account_number(),
        account_type=validated['account_type'],
        currency=validated['currency'],
        user_id=get_jwt_identity()
    )
    db.session.add(account)
    db.session.commit()
    return jsonify({'message': 'Account created', 'account': account.to_dict()}), 201

@transactions_bp.route('/deposit', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def deposit():
    data = request.get_json()
    try:
        validated = DepositSchema().load(data)
    except ValidationError as err:
        return handle_validation_error(err)
    account = Account.query.filter_by(id=validated['account_id'], user_id=get_jwt_identity()).first()
    if not account:
        return jsonify({'error': 'Account not found', 'status': 404}), 404
    amount = validated['amount']
    account.balance += amount
    txn = Transaction(amount=amount, type='deposit', status='completed',
                      reference=generate_transaction_reference(), to_account_id=account.id)
    db.session.add(txn)
    db.session.commit()
    return jsonify({'message': 'Deposit successful', 'new_balance': str(account.balance),
                    'transaction_id': txn.id}), 200

@transactions_bp.route('/withdraw', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def withdraw():
    data = request.get_json()
    try:
        validated = WithdrawSchema().load(data)
    except ValidationError as err:
        return handle_validation_error(err)
    account = Account.query.filter_by(id=validated['account_id'], user_id=get_jwt_identity()).first()
    if not account:
        return jsonify({'error': 'Account not found', 'status': 404}), 404
    amount = validated['amount']
    if account.balance < amount:
        return jsonify({'error': 'Insufficient funds', 'status': 400}), 400
    account.balance -= amount
    txn = Transaction(amount=amount, type='withdrawal', status='completed',
                      reference=generate_transaction_reference(), from_account_id=account.id)
    db.session.add(txn)
    db.session.commit()
    return jsonify({'message': 'Withdrawal successful', 'new_balance': str(account.balance),
                    'transaction_id': txn.id}), 200

@transactions_bp.route('/transfer', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def transfer():
    data = request.get_json()
    try:
        validated = TransferSchema().load(data)
    except ValidationError as err:
        return handle_validation_error(err)
    src = Account.query.filter_by(id=validated['from_account_id'], user_id=get_jwt_identity()).first()
    if not src:
        return jsonify({'error': 'Source account not found', 'status': 404}), 404
    dst = Account.query.filter_by(id=validated['to_account_id']).first()
    if not dst:
        return jsonify({'error': 'Destination account not found', 'status': 404}), 404
    amount = validated['amount']
    if src.balance < amount:
        return jsonify({'error': 'Insufficient funds', 'status': 400}), 400
    src.balance -= amount
    dst.balance += amount
    txn = Transaction(amount=amount, type='transfer', status='completed',
                      description=validated['description'],
                      reference=generate_transaction_reference(),
                      from_account_id=src.id, to_account_id=dst.id)
    db.session.add(txn)
    db.session.commit()
    return jsonify({'message': 'Transfer successful', 'source_balance': str(src.balance),
                    'destination_account': dst.account_number, 'transaction_id': txn.id}), 200

@transactions_bp.route('/history', methods=['GET'])
@jwt_required()
def transaction_history():
    user_accounts = Account.query.filter_by(user_id=get_jwt_identity()).all()
    ids = [a.id for a in user_accounts]
    txns = Transaction.query.filter(
        db.or_(Transaction.from_account_id.in_(ids), Transaction.to_account_id.in_(ids))
    ).order_by(Transaction.created_at.desc()).limit(100).all()
    return jsonify({'transactions': [t.to_dict() for t in txns], 'count': len(txns)}), 200

# ----------------------------------------------------------------------
# 10. Run
# ----------------------------------------------------------------------

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0' if os.environ.get('FLASK_ENV') == 'production' else '127.0.0.1')
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host=host, port=port, debug=debug)
