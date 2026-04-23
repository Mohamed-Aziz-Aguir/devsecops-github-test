# app/app.py
"""
Production banking backend with JWT authentication, PostgreSQL,
and core banking operations (deposit, withdraw, transfer).
Public landing page accessible without login.
Account-specific features require authentication.
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
# 1. Configuration
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
        'DATABASE_URL', 'postgresql://bankuser:bankpass@localhost:5432/bankdb')
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
# 3. HTML
# ----------------------------------------------------------------------

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SecureBank</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --navy: #0d1b2a; --blue: #1565c0; --blue-light: #1976d2; --accent: #4fc3f7;
  --green: #2e7d32; --orange: #e65100; --red: #c62828;
  --bg: #f4f6fb; --card: #ffffff; --border: #e0e7ef;
  --text: #1a1a2e; --muted: #6b7280; --shadow: 0 2px 12px rgba(0,0,0,.08);
}
body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); }

/* ── NAV ── */
nav {
  background: var(--navy); color: #fff; height: 64px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 2rem; position: sticky; top: 0; z-index: 100;
  box-shadow: 0 2px 16px rgba(0,0,0,.3);
}
.brand { font-size: 1.25rem; font-weight: 800; color: var(--accent); letter-spacing: 1px; cursor: pointer; }
.brand span { color: #fff; }
.nav-right { display: flex; align-items: center; gap: .8rem; }
.nav-links { display: flex; gap: .2rem; }
.nav-link {
  color: #cbd5e1; background: transparent; border: none; padding: .45rem .9rem;
  border-radius: 6px; cursor: pointer; font-size: .88rem; transition: all .15s;
}
.nav-link:hover { background: rgba(255,255,255,.1); color: #fff; }
.nav-link.active { color: var(--accent); }
#nav-user { color: #94a3b8; font-size: .85rem; }
.btn-nav {
  padding: .42rem 1rem; border-radius: 20px; font-size: .85rem; font-weight: 600;
  cursor: pointer; transition: all .2s; border: none;
}
.btn-nav-outline { background: transparent; border: 1.5px solid var(--accent); color: var(--accent); }
.btn-nav-outline:hover { background: var(--accent); color: var(--navy); }
.btn-nav-fill { background: var(--blue); color: #fff; }
.btn-nav-fill:hover { background: var(--blue-light); }

/* ── PAGES ── */
.page { display: none; }
.page.active { display: block; }

/* ── HERO ── */
.hero {
  background: linear-gradient(135deg, var(--navy) 0%, #1a3a5c 60%, #1565c0 100%);
  color: #fff; padding: 5rem 2rem 4rem; text-align: center;
}
.hero h1 { font-size: clamp(2rem, 5vw, 3.2rem); font-weight: 800; line-height: 1.15; }
.hero h1 span { color: var(--accent); }
.hero p { font-size: 1.1rem; color: #94a3b8; margin: 1.2rem auto 2rem; max-width: 540px; line-height: 1.7; }
.hero-btns { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }
.btn-hero-primary {
  padding: .85rem 2.2rem; background: var(--accent); color: var(--navy);
  border: none; border-radius: 30px; font-size: 1rem; font-weight: 700; cursor: pointer; transition: all .2s;
}
.btn-hero-primary:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(79,195,247,.4); }
.btn-hero-secondary {
  padding: .85rem 2.2rem; background: transparent; color: #fff;
  border: 2px solid rgba(255,255,255,.35); border-radius: 30px;
  font-size: 1rem; font-weight: 600; cursor: pointer; transition: all .2s;
}
.btn-hero-secondary:hover { border-color: #fff; background: rgba(255,255,255,.08); }

/* ── FEATURES SECTION ── */
.section { padding: 4rem 2rem; max-width: 1100px; margin: 0 auto; }
.section-title { font-size: 1.7rem; font-weight: 800; text-align: center; margin-bottom: .6rem; }
.section-sub { text-align: center; color: var(--muted); margin-bottom: 2.5rem; font-size: 1rem; }
.features-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; }
.feature-card {
  background: var(--card); border-radius: 14px; padding: 2rem 1.5rem;
  box-shadow: var(--shadow); border: 1px solid var(--border); transition: transform .2s;
}
.feature-card:hover { transform: translateY(-4px); }
.feature-icon { font-size: 2rem; margin-bottom: 1rem; }
.feature-card h3 { font-size: 1.05rem; font-weight: 700; margin-bottom: .5rem; }
.feature-card p { color: var(--muted); font-size: .9rem; line-height: 1.6; }

/* ── RATES TICKER ── */
.rates-bar {
  background: var(--navy); color: #94a3b8; padding: .7rem 2rem;
  display: flex; gap: 2.5rem; overflow-x: auto; font-size: .85rem; align-items: center;
}
.rates-bar .rate-item { display: flex; gap: .5rem; white-space: nowrap; align-items: center; }
.rates-bar .rate-name { color: var(--accent); font-weight: 600; }
.rate-up { color: #4ade80; }
.rate-down { color: #f87171; }

/* ── HOW IT WORKS ── */
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; }
.step { text-align: center; padding: 1.5rem; }
.step-num {
  width: 48px; height: 48px; background: var(--blue); color: #fff; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.2rem; font-weight: 800; margin: 0 auto 1rem;
}
.step h4 { font-weight: 700; margin-bottom: .4rem; }
.step p { color: var(--muted); font-size: .88rem; line-height: 1.6; }

/* ── STATS BAR ── */
.stats-bar {
  background: var(--blue); color: #fff; padding: 2.5rem 2rem;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1.5rem; text-align: center;
}
.stat-item .num { font-size: 2.2rem; font-weight: 800; }
.stat-item .lbl { font-size: .85rem; opacity: .8; margin-top: .2rem; }

/* ── DASHBOARD ── */
.dash-wrap { max-width: 1100px; margin: 0 auto; padding: 2rem; }
.dash-header { margin-bottom: 2rem; }
.dash-header h1 { font-size: 1.7rem; font-weight: 800; }
.dash-header p { color: var(--muted); margin-top: .3rem; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1.2rem; margin-bottom: 2rem; }
.sum-card {
  background: var(--card); border-radius: 12px; padding: 1.4rem;
  box-shadow: var(--shadow); border: 1px solid var(--border);
}
.sum-card .lbl { font-size: .75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; }
.sum-card .val { font-size: 1.9rem; font-weight: 800; color: var(--text); margin-top: .3rem; }
.sum-card .sub { font-size: .78rem; color: #aaa; margin-top: .2rem; }
.panel-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }
@media(max-width:700px) { .panel-row { grid-template-columns: 1fr; } }
.panel {
  background: var(--card); border-radius: 12px; padding: 1.5rem;
  box-shadow: var(--shadow); border: 1px solid var(--border);
}
.panel h3 {
  font-size: .95rem; font-weight: 700; margin-bottom: 1.2rem;
  padding-bottom: .7rem; border-bottom: 2px solid #e3f2fd; color: var(--text);
}
.acc-card {
  background: linear-gradient(135deg, #1565c0, #0d47a1); color: #fff;
  border-radius: 10px; padding: 1rem 1.2rem; display: flex;
  justify-content: space-between; align-items: center; margin-bottom: .7rem;
}
.acc-num { font-size: .78rem; opacity: .8; font-family: monospace; }
.acc-type { font-size: .82rem; text-transform: capitalize; opacity: .85; margin-top: .1rem; }
.acc-bal { font-size: 1.25rem; font-weight: 800; }
.acc-cur { font-size: .72rem; opacity: .75; }
.empty { text-align: center; color: #bbb; font-size: .88rem; padding: 1.5rem 0; }

/* ── TABS ── */
.tabs { display: flex; gap: .5rem; margin-bottom: 1.2rem; flex-wrap: wrap; }
.tab {
  padding: .42rem 1.1rem; border-radius: 20px; font-size: .83rem; font-weight: 600;
  cursor: pointer; border: 2px solid var(--border); background: #fff; color: var(--muted); transition: all .15s;
}
.tab.active { border-color: var(--blue); background: var(--blue); color: #fff; }

/* ── FORM ── */
.fg { margin-bottom: .9rem; }
.fg label { display: block; font-size: .8rem; font-weight: 600; color: #555; margin-bottom: .35rem; }
.fg input, .fg select {
  width: 100%; padding: .6rem .85rem; border: 1.5px solid var(--border);
  border-radius: 8px; font-size: .92rem; outline: none; transition: border .15s;
}
.fg input:focus, .fg select:focus { border-color: var(--blue); }

/* ── BUTTONS ── */
.btn {
  padding: .6rem 1.3rem; border: none; border-radius: 8px; cursor: pointer;
  font-size: .88rem; font-weight: 700; transition: all .15s;
}
.btn-primary { background: var(--blue); color: #fff; width: 100%; margin-top: .4rem; }
.btn-primary:hover { background: var(--blue-light); }
.btn-green { background: var(--green); color: #fff; }
.btn-green:hover { background: #1b5e20; }
.btn-orange { background: var(--orange); color: #fff; }
.btn-orange:hover { background: #bf360c; }
.btn-teal { background: #01579b; color: #fff; }
.btn-teal:hover { background: #003c6e; }
.btn-ghost { background: #f1f5f9; color: #333; }
.btn-ghost:hover { background: #e2e8f0; }

/* ── ALERT ── */
.alert { padding: .7rem 1rem; border-radius: 8px; font-size: .88rem; display: none; margin-bottom: .9rem; }
.alert.show { display: block; }
.alert-err { background: #fef2f2; color: var(--red); border: 1px solid #fca5a5; }
.alert-ok  { background: #f0fdf4; color: var(--green); border: 1px solid #86efac; }

/* ── TABLE ── */
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .87rem; }
th { background: #f8fafc; padding: .65rem 1rem; text-align: left; font-size: .76rem;
     text-transform: uppercase; letter-spacing: .4px; color: var(--muted); }
td { padding: .65rem 1rem; border-bottom: 1px solid #f1f5f9; }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: .18rem .6rem; border-radius: 10px; font-size: .74rem; font-weight: 700; }
.b-deposit    { background: #dcfce7; color: #166534; }
.b-withdrawal { background: #fff7ed; color: #9a3412; }
.b-transfer   { background: #eff6ff; color: #1e40af; }
.b-completed  { background: #dcfce7; color: #166534; }
.b-pending    { background: #fefce8; color: #854d0e; }

/* ── MODAL ── */
.overlay {
  display: none; position: fixed; inset: 0; background: rgba(0,0,0,.55);
  z-index: 200; align-items: center; justify-content: center;
}
.overlay.open { display: flex; }
.modal {
  background: var(--card); border-radius: 14px; padding: 2rem;
  width: 100%; max-width: 400px; box-shadow: 0 12px 40px rgba(0,0,0,.25);
}
.modal h3 { font-size: 1.1rem; font-weight: 800; margin-bottom: 1.2rem; }
.modal-footer { display: flex; gap: .7rem; margin-top: .8rem; }

/* ── AUTH MODAL ── */
.auth-tabs { display: flex; margin-bottom: 1.5rem; border-bottom: 2px solid var(--border); }
.auth-tab {
  flex: 1; padding: .7rem; text-align: center; cursor: pointer;
  font-weight: 600; font-size: .9rem; color: var(--muted); border-bottom: 2px solid transparent;
  margin-bottom: -2px; transition: all .15s;
}
.auth-tab.active { color: var(--blue); border-bottom-color: var(--blue); }

/* ── FOOTER ── */
footer {
  background: var(--navy); color: #64748b; text-align: center;
  padding: 2rem; font-size: .85rem; margin-top: 3rem;
}
footer span { color: var(--accent); }
</style>
</head>
<body>

<!-- ═══════════════════════════════ NAV ═══════════════════════════════ -->
<nav>
  <div class="brand" onclick="goHome()">Secure<span>Bank</span></div>
  <div class="nav-right">
    <div class="nav-links">
      <button class="nav-link active" onclick="goHome()">Home</button>
      <button class="nav-link" onclick="goTo('features')">Features</button>
      <button class="nav-link" onclick="goTo('how')">How it works</button>
    </div>
    <span id="nav-user"></span>
    <button class="btn-nav btn-nav-outline" id="btn-login-nav" onclick="openAuth('login')">Login</button>
    <button class="btn-nav btn-nav-fill"    id="btn-signup-nav" onclick="openAuth('register')">Sign up</button>
    <button class="btn-nav btn-nav-fill"    id="btn-dash-nav" style="display:none" onclick="showDash()">Dashboard</button>
    <button class="btn-nav btn-nav-outline" id="btn-logout-nav" style="display:none" onclick="doLogout()">Logout</button>
  </div>
</nav>

<!-- ═══════════════════════════════ HOME PAGE ═══════════════════════════════ -->
<div id="page-home" class="page active">

  <!-- Hero -->
  <div class="hero">
    <h1>Banking made <span>simple</span><br>and secure</h1>
    <p>Open accounts, transfer money, and track every transaction — all in one place, protected by enterprise-grade security.</p>
    <div class="hero-btns">
      <button class="btn-hero-primary" onclick="openAuth('register')">Get started — it's free</button>
      <button class="btn-hero-secondary" onclick="goTo('features')">Learn more</button>
    </div>
  </div>

  <!-- Live rates ticker -->
  <div class="rates-bar" id="rates-bar">
    <div class="rate-item"><span class="rate-name">EUR/USD</span><span id="r-eurusd">1.0842</span> <span class="rate-up">▲</span></div>
    <div class="rate-item"><span class="rate-name">GBP/USD</span><span id="r-gbpusd">1.2734</span> <span class="rate-up">▲</span></div>
    <div class="rate-item"><span class="rate-name">USD/JPY</span><span id="r-usdjpy">154.32</span> <span class="rate-down">▼</span></div>
    <div class="rate-item"><span class="rate-name">BTC/USD</span><span id="r-btcusd">67,420</span> <span class="rate-up">▲</span></div>
    <div class="rate-item"><span class="rate-name">ETH/USD</span><span id="r-ethusd">3,512</span> <span class="rate-up">▲</span></div>
    <div class="rate-item"><span class="rate-name">Gold</span><span id="r-gold">2,341</span> <span class="rate-down">▼</span></div>
  </div>

  <!-- Features -->
  <div class="section" id="features">
    <div class="section-title">Everything you need</div>
    <div class="section-sub">Built for individuals who want full control of their finances</div>
    <div class="features-grid">
      <div class="feature-card">
        <div class="feature-icon">🔒</div>
        <h3>Bank-grade security</h3>
        <p>JWT authentication, bcrypt password hashing, rate limiting, and TLS encryption on every request.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">⚡</div>
        <h3>Instant transfers</h3>
        <p>Send money between accounts in seconds. Every transaction is logged with a unique reference number.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📊</div>
        <h3>Full transaction history</h3>
        <p>Browse your last 100 transactions with type badges, amounts, status, and timestamps.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🏦</div>
        <h3>Multiple accounts</h3>
        <p>Open checking and savings accounts in USD, EUR, or GBP — all under one login.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📈</div>
        <h3>Live monitoring</h3>
        <p>Prometheus metrics exposed at /metrics for real-time observability and alerting.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🛡️</div>
        <h3>DevSecOps pipeline</h3>
        <p>Every deploy passes SAST, DAST, Trivy, Falco, SonarQube, and Kyverno policy gates.</p>
      </div>
    </div>
  </div>

  <!-- Stats bar -->
  <div class="stats-bar">
    <div class="stat-item"><div class="num">99.9%</div><div class="lbl">Uptime SLA</div></div>
    <div class="stat-item"><div class="num">&lt;50ms</div><div class="lbl">Avg response time</div></div>
    <div class="stat-item"><div class="num">AES-256</div><div class="lbl">Data encryption</div></div>
    <div class="stat-item"><div class="num">24/7</div><div class="lbl">Monitoring active</div></div>
  </div>

  <!-- How it works -->
  <div class="section" id="how">
    <div class="section-title">How it works</div>
    <div class="section-sub">Up and running in under a minute</div>
    <div class="steps">
      <div class="step">
        <div class="step-num">1</div>
        <h4>Create your account</h4>
        <p>Register with a username, email, and password. Your credentials are hashed and never stored in plain text.</p>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <h4>Open a bank account</h4>
        <p>Choose between checking and savings in your preferred currency. Your account number is generated instantly.</p>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <h4>Deposit funds</h4>
        <p>Add money to your account. Every deposit is recorded with a unique transaction reference.</p>
      </div>
      <div class="step">
        <div class="step-num">4</div>
        <h4>Transfer & track</h4>
        <p>Send money to any account and monitor your full transaction history in real time.</p>
      </div>
    </div>
  </div>

  <!-- CTA -->
  <div style="background:linear-gradient(135deg,#1565c0,#0d47a1);color:#fff;text-align:center;padding:4rem 2rem;">
    <h2 style="font-size:1.8rem;font-weight:800;margin-bottom:.8rem">Ready to get started?</h2>
    <p style="color:#90caf9;margin-bottom:1.8rem">Join SecureBank today — free, fast, and fully secured.</p>
    <button class="btn-hero-primary" onclick="openAuth('register')">Create free account</button>
  </div>

</div><!-- end page-home -->

<!-- ═══════════════════════════════ DASHBOARD PAGE ═══════════════════════════════ -->
<div id="page-dashboard" class="page">
  <div class="dash-wrap">

    <div class="dash-header">
      <h1>Dashboard</h1>
      <p id="dash-sub">Overview of your accounts and activity</p>
    </div>

    <div class="summary-grid">
      <div class="sum-card">
        <div class="lbl">Total Balance</div>
        <div class="val" id="s-total">$0.00</div>
        <div class="sub">Across all accounts</div>
      </div>
      <div class="sum-card">
        <div class="lbl">Accounts</div>
        <div class="val" id="s-accs">0</div>
        <div class="sub">Active</div>
      </div>
      <div class="sum-card">
        <div class="lbl">Transactions</div>
        <div class="val" id="s-txns">0</div>
        <div class="sub">Total recorded</div>
      </div>
    </div>

    <div class="panel-row">
      <!-- Accounts list -->
      <div class="panel">
        <h3>My Accounts</h3>
        <div id="acc-list"><div class="empty">No accounts yet</div></div>
      </div>

      <!-- Quick actions -->
      <div class="panel">
        <h3>Quick Actions</h3>
        <div class="tabs">
          <div class="tab active" onclick="switchTab('dep')">Deposit</div>
          <div class="tab"       onclick="switchTab('with')">Withdraw</div>
          <div class="tab"       onclick="switchTab('trf')">Transfer</div>
        </div>
        <div id="act-alert" class="alert"></div>

        <div id="tab-dep">
          <div class="fg"><label>Account</label><select id="d-acc"></select></div>
          <div class="fg"><label>Amount (USD)</label><input type="number" id="d-amt" placeholder="0.00" min="0.01" step="0.01"/></div>
          <button class="btn btn-green" onclick="doDeposit()">Deposit</button>
        </div>

        <div id="tab-with" style="display:none">
          <div class="fg"><label>Account</label><select id="w-acc"></select></div>
          <div class="fg"><label>Amount (USD)</label><input type="number" id="w-amt" placeholder="0.00" min="0.01" step="0.01"/></div>
          <button class="btn btn-orange" onclick="doWithdraw()">Withdraw</button>
        </div>

        <div id="tab-trf" style="display:none">
          <div class="fg"><label>From</label><select id="t-from"></select></div>
          <div class="fg"><label>To Account ID</label><input type="number" id="t-to" placeholder="Destination account ID"/></div>
          <div class="fg"><label>Amount (USD)</label><input type="number" id="t-amt" placeholder="0.00" min="0.01" step="0.01"/></div>
          <div class="fg"><label>Description</label><input type="text" id="t-desc" placeholder="Optional note"/></div>
          <button class="btn btn-teal" onclick="doTransfer()">Send Transfer</button>
        </div>
      </div>
    </div>

    <!-- Transaction history -->
    <div class="panel">
      <h3>Transaction History</h3>
      <div class="tbl-wrap">
        <table>
          <thead><tr><th>Reference</th><th>Type</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead>
          <tbody id="txn-body"><tr><td colspan="5" class="empty">No transactions yet</td></tr></tbody>
        </table>
      </div>
    </div>

  </div>
</div><!-- end page-dashboard -->

<!-- ═══════════════════════════════ AUTH MODAL ═══════════════════════════════ -->
<div class="overlay" id="auth-overlay">
  <div class="modal">
    <div class="auth-tabs">
      <div class="auth-tab active" id="tab-login-btn" onclick="switchAuth('login')">Login</div>
      <div class="auth-tab"        id="tab-reg-btn"   onclick="switchAuth('register')">Register</div>
    </div>
    <div id="auth-alert" class="alert"></div>

    <div id="auth-login">
      <div class="fg"><label>Username</label><input type="text" id="l-user" placeholder="Username"/></div>
      <div class="fg"><label>Password</label><input type="password" id="l-pass" placeholder="Password"/></div>
      <button class="btn btn-primary" onclick="doLogin()">Sign In</button>
    </div>

    <div id="auth-register" style="display:none">
      <div class="fg"><label>Username</label><input type="text" id="r-user" placeholder="Choose username"/></div>
      <div class="fg"><label>Email</label><input type="email" id="r-email" placeholder="your@email.com"/></div>
      <div class="fg"><label>Password</label><input type="password" id="r-pass" placeholder="Min 6 characters"/></div>
      <button class="btn btn-primary" onclick="doRegister()">Create Account</button>
    </div>

    <div style="text-align:right;margin-top:.8rem">
      <button class="btn btn-ghost" style="font-size:.8rem" onclick="closeAuth()">Cancel</button>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════ NEW ACCOUNT MODAL ═══════════════════════════════ -->
<div class="overlay" id="acc-overlay">
  <div class="modal">
    <h3>Open New Account</h3>
    <div id="acc-modal-alert" class="alert"></div>
    <div class="fg"><label>Account Type</label>
      <select id="na-type"><option value="checking">Checking</option><option value="savings">Savings</option></select>
    </div>
    <div class="fg"><label>Currency</label>
      <select id="na-cur"><option value="USD">USD</option><option value="EUR">EUR</option><option value="GBP">GBP</option></select>
    </div>
    <div class="modal-footer">
      <button class="btn btn-primary" style="width:auto" onclick="doCreateAccount()">Open Account</button>
      <button class="btn btn-ghost" onclick="closeAccModal()">Cancel</button>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════ FOOTER ═══════════════════════════════ -->
<footer>
  <span>SecureBank</span> &mdash; DevSecOps demo &bull; Deployed on Kubernetes &bull; Protected by Kyverno + Falco + Trivy
</footer>

<script>
// ──────────────────────────────────────────────────────
// State
// ──────────────────────────────────────────────────────
let token = localStorage.getItem('sb_token') || null;
let user  = null;
let accounts = [];

// ──────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  tickRates();
  setInterval(tickRates, 3000);
  if (token) restoreSession();
});

// ──────────────────────────────────────────────────────
// Fake live rates ticker
// ──────────────────────────────────────────────────────
const rateSeeds = { eurusd:1.0842, gbpusd:1.2734, usdjpy:154.32, btcusd:67420, ethusd:3512, gold:2341 };
function tickRates() {
  const jitter = v => (v * (1 + (Math.random()-.5)*.002)).toFixed(v>100?0:4);
  document.getElementById('r-eurusd').textContent = jitter(rateSeeds.eurusd);
  document.getElementById('r-gbpusd').textContent = jitter(rateSeeds.gbpusd);
  document.getElementById('r-usdjpy').textContent = jitter(rateSeeds.usdjpy);
  document.getElementById('r-btcusd').textContent = Number(jitter(rateSeeds.btcusd)).toLocaleString();
  document.getElementById('r-ethusd').textContent = Number(jitter(rateSeeds.ethusd)).toLocaleString();
  document.getElementById('r-gold').textContent   = Number(jitter(rateSeeds.gold)).toLocaleString();
}

// ──────────────────────────────────────────────────────
// Navigation
// ──────────────────────────────────────────────────────
function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
}

function goHome() { showPage('home'); }

function goTo(id) {
  showPage('home');
  setTimeout(() => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  }, 50);
}

function showDash() {
  showPage('dashboard');
  loadAccounts();
  loadTransactions();
}

// ──────────────────────────────────────────────────────
// Auth modal
// ──────────────────────────────────────────────────────
function openAuth(tab) {
  switchAuth(tab);
  hideAlert('auth-alert');
  document.getElementById('auth-overlay').classList.add('open');
}

function closeAuth() {
  document.getElementById('auth-overlay').classList.remove('open');
}

function switchAuth(tab) {
  document.getElementById('auth-login').style.display    = tab === 'login'    ? 'block' : 'none';
  document.getElementById('auth-register').style.display = tab === 'register' ? 'block' : 'none';
  document.getElementById('tab-login-btn').classList.toggle('active', tab === 'login');
  document.getElementById('tab-reg-btn').classList.toggle('active',   tab === 'register');
  hideAlert('auth-alert');
}

// Close overlay on backdrop click
document.getElementById('auth-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('auth-overlay')) closeAuth();
});

// ──────────────────────────────────────────────────────
// Alerts
// ──────────────────────────────────────────────────────
function showAlert(id, msg, type) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.className = 'alert show alert-' + (type === 'ok' ? 'ok' : 'err');
}
function hideAlert(id) { document.getElementById(id).className = 'alert'; }

// ──────────────────────────────────────────────────────
// API
// ──────────────────────────────────────────────────────
async function api(method, path, body, auth) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth && token) headers['Authorization'] = 'Bearer ' + token;
  const res  = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

// ──────────────────────────────────────────────────────
// Session
// ──────────────────────────────────────────────────────
function onLoggedIn(data) {
  token = data.access_token;
  user  = data.user;
  localStorage.setItem('sb_token', token);
  document.getElementById('nav-user').textContent     = user.username;
  document.getElementById('btn-login-nav').style.display  = 'none';
  document.getElementById('btn-signup-nav').style.display = 'none';
  document.getElementById('btn-dash-nav').style.display   = 'inline-block';
  document.getElementById('btn-logout-nav').style.display = 'inline-block';
  closeAuth();
  showDash();
}

async function restoreSession() {
  const { ok, data } = await api('GET', '/accounts', null, true);
  if (!ok) { doLogout(); return; }
  accounts = data.accounts;
  document.getElementById('btn-login-nav').style.display  = 'none';
  document.getElementById('btn-signup-nav').style.display = 'none';
  document.getElementById('btn-dash-nav').style.display   = 'inline-block';
  document.getElementById('btn-logout-nav').style.display = 'inline-block';
}

function doLogout() {
  token = null; user = null; accounts = [];
  localStorage.removeItem('sb_token');
  document.getElementById('nav-user').textContent     = '';
  document.getElementById('btn-login-nav').style.display  = 'inline-block';
  document.getElementById('btn-signup-nav').style.display = 'inline-block';
  document.getElementById('btn-dash-nav').style.display   = 'none';
  document.getElementById('btn-logout-nav').style.display = 'none';
  goHome();
}

// ──────────────────────────────────────────────────────
// Auth actions
// ──────────────────────────────────────────────────────
async function doLogin() {
  const username = document.getElementById('l-user').value.trim();
  const password = document.getElementById('l-pass').value;
  if (!username || !password) return showAlert('auth-alert', 'Fill in all fields.');
  const { ok, data } = await api('POST', '/auth/login', { username, password });
  if (!ok) return showAlert('auth-alert', data.error || 'Login failed.');
  onLoggedIn(data);
}

async function doRegister() {
  const username = document.getElementById('r-user').value.trim();
  const email    = document.getElementById('r-email').value.trim();
  const password = document.getElementById('r-pass').value;
  if (!username || !email || !password) return showAlert('auth-alert', 'Fill in all fields.');
  const { ok, data } = await api('POST', '/auth/register', { username, email, password });
  if (!ok) return showAlert('auth-alert', data.error || 'Registration failed.');
  onLoggedIn(data);
}

// ──────────────────────────────────────────────────────
// Dashboard data
// ──────────────────────────────────────────────────────
async function loadAccounts() {
  const { ok, data } = await api('GET', '/accounts', null, true);
  if (!ok) { if (data.status === 401) doLogout(); return; }
  accounts = data.accounts;

  document.getElementById('s-accs').textContent = accounts.length;
  const total = accounts.reduce((s, a) => s + parseFloat(a.balance), 0);
  document.getElementById('s-total').textContent = '$' + total.toFixed(2);
  if (user) document.getElementById('dash-sub').textContent = 'Welcome back, ' + user.username;

  const list = document.getElementById('acc-list');
  if (!accounts.length) {
    list.innerHTML = `<div class="empty">No accounts yet —
      <a href="#" style="color:var(--blue)" onclick="openAccModal();return false">open one</a></div>`;
  } else {
    list.innerHTML = accounts.map(a => `
      <div class="acc-card">
        <div>
          <div class="acc-num">${a.account_number}</div>
          <div class="acc-type">${a.account_type}</div>
        </div>
        <div style="text-align:right">
          <div class="acc-bal">$${parseFloat(a.balance).toFixed(2)}</div>
          <div class="acc-cur">${a.currency}</div>
        </div>
      </div>`).join('') +
      `<button class="btn btn-ghost" style="width:100%;margin-top:.5rem;font-size:.82rem"
         onclick="openAccModal()">+ Open another account</button>`;
  }

  const opts = accounts.map(a =>
    `<option value="${a.id}">${a.account_number} ($${parseFloat(a.balance).toFixed(2)})</option>`
  ).join('');
  ['d-acc','w-acc','t-from'].forEach(id => {
    document.getElementById(id).innerHTML = opts || '<option>No accounts</option>';
  });
}

async function loadTransactions() {
  const { ok, data } = await api('GET', '/transactions/history', null, true);
  if (!ok) return;
  document.getElementById('s-txns').textContent = data.count;
  const tbody = document.getElementById('txn-body');
  if (!data.count) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">No transactions yet</td></tr>';
    return;
  }
  tbody.innerHTML = data.transactions.map(t => `
    <tr>
      <td style="font-family:monospace;font-size:.78rem">${t.reference || '-'}</td>
      <td><span class="badge b-${t.type}">${t.type}</span></td>
      <td><strong>$${parseFloat(t.amount).toFixed(2)}</strong></td>
      <td><span class="badge b-${t.status}">${t.status}</span></td>
      <td style="color:var(--muted);font-size:.82rem">${new Date(t.created_at).toLocaleString()}</td>
    </tr>`).join('');
}

// ──────────────────────────────────────────────────────
// Quick action tabs
// ──────────────────────────────────────────────────────
function switchTab(name) {
  ['dep','with','trf'].forEach(t => {
    document.getElementById('tab-' + t).style.display = t === name ? 'block' : 'none';
  });
  document.querySelectorAll('.tabs .tab').forEach((btn, i) => {
    btn.classList.toggle('active', ['dep','with','trf'][i] === name);
  });
  hideAlert('act-alert');
}

// ──────────────────────────────────────────────────────
// Transactions
// ──────────────────────────────────────────────────────
async function doDeposit() {
  const account_id = parseInt(document.getElementById('d-acc').value);
  const amount     = parseFloat(document.getElementById('d-amt').value);
  if (!amount || amount <= 0) return showAlert('act-alert', 'Enter a valid amount.');
  const { ok, data } = await api('POST', '/transactions/deposit', { account_id, amount }, true);
  if (!ok) return showAlert('act-alert', data.error || 'Deposit failed.');
  showAlert('act-alert', `Deposited $${amount.toFixed(2)} — new balance: $${parseFloat(data.new_balance).toFixed(2)}`, 'ok');
  document.getElementById('d-amt').value = '';
  await loadAccounts(); await loadTransactions();
}

async function doWithdraw() {
  const account_id = parseInt(document.getElementById('w-acc').value);
  const amount     = parseFloat(document.getElementById('w-amt').value);
  if (!amount || amount <= 0) return showAlert('act-alert', 'Enter a valid amount.');
  const { ok, data } = await api('POST', '/transactions/withdraw', { account_id, amount }, true);
  if (!ok) return showAlert('act-alert', data.error || 'Withdrawal failed.');
  showAlert('act-alert', `Withdrew $${amount.toFixed(2)} — new balance: $${parseFloat(data.new_balance).toFixed(2)}`, 'ok');
  document.getElementById('w-amt').value = '';
  await loadAccounts(); await loadTransactions();
}

async function doTransfer() {
  const from_account_id = parseInt(document.getElementById('t-from').value);
  const to_account_id   = parseInt(document.getElementById('t-to').value);
  const amount          = parseFloat(document.getElementById('t-amt').value);
  const description     = document.getElementById('t-desc').value;
  if (!to_account_id || !amount || amount <= 0)
    return showAlert('act-alert', 'Fill in all transfer fields.');
  const { ok, data } = await api('POST', '/transactions/transfer',
    { from_account_id, to_account_id, amount, description }, true);
  if (!ok) return showAlert('act-alert', data.error || 'Transfer failed.');
  showAlert('act-alert', `Sent $${amount.toFixed(2)} — your balance: $${parseFloat(data.source_balance).toFixed(2)}`, 'ok');
  ['t-to','t-amt','t-desc'].forEach(id => document.getElementById(id).value = '');
  await loadAccounts(); await loadTransactions();
}

// ──────────────────────────────────────────────────────
// New account modal
// ──────────────────────────────────────────────────────
function openAccModal() {
  hideAlert('acc-modal-alert');
  document.getElementById('acc-overlay').classList.add('open');
}
function closeAccModal() {
  document.getElementById('acc-overlay').classList.remove('open');
}
document.getElementById('acc-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('acc-overlay')) closeAccModal();
});

async function doCreateAccount() {
  const account_type = document.getElementById('na-type').value;
  const currency     = document.getElementById('na-cur').value;
  const { ok, data } = await api('POST', '/accounts', { account_type, currency }, true);
  if (!ok) return showAlert('acc-modal-alert', data.error || 'Failed.');
  closeAccModal();
  await loadAccounts();
}

// Enter key in auth modal
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  if (!document.getElementById('auth-overlay').classList.contains('open')) return;
  if (document.getElementById('auth-login').style.display !== 'none') doLogin();
  else doRegister();
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
            'style-src':  ["'self'", "'unsafe-inline'"],
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

    app.register_blueprint(auth_bp,         url_prefix='/auth')
    app.register_blueprint(accounts_bp,     url_prefix='/accounts')
    app.register_blueprint(transactions_bp, url_prefix='/transactions')

    app.config['START_TIME'] = time.time()
    return app

# ----------------------------------------------------------------------
# 5. Models
# ----------------------------------------------------------------------

class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    is_active     = db.Column(db.Boolean,  default=True)
    accounts      = db.relationship('Account', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {'id': self.id, 'username': self.username, 'email': self.email,
                'created_at': self.created_at.isoformat(), 'is_active': self.is_active}


class Account(db.Model):
    __tablename__ = 'accounts'
    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20),    unique=True, nullable=False)
    account_type   = db.Column(db.String(20),    nullable=False, default='checking')
    balance        = db.Column(db.Numeric(10,2), nullable=False, default=0.00)
    currency       = db.Column(db.String(3),     nullable=False, default='USD')
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    outgoing_transactions = db.relationship(
        'Transaction', foreign_keys='Transaction.from_account_id', backref='source')
    incoming_transactions = db.relationship(
        'Transaction', foreign_keys='Transaction.to_account_id', backref='destination')

    def to_dict(self):
        return {'id': self.id, 'account_number': self.account_number,
                'account_type': self.account_type, 'balance': str(self.balance),
                'currency': self.currency, 'created_at': self.created_at.isoformat()}


class Transaction(db.Model):
    __tablename__   = 'transactions'
    id              = db.Column(db.Integer, primary_key=True)
    amount          = db.Column(db.Numeric(10,2), nullable=False)
    type            = db.Column(db.String(20), nullable=False)
    status          = db.Column(db.String(20), nullable=False, default='pending')
    description     = db.Column(db.String(200))
    reference       = db.Column(db.String(50), unique=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    from_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    to_account_id   = db.Column(db.Integer, db.ForeignKey('accounts.id'))

    def to_dict(self):
        return {'id': self.id, 'amount': str(self.amount), 'type': self.type,
                'status': self.status, 'description': self.description,
                'reference': self.reference, 'created_at': self.created_at.isoformat(),
                'from_account': self.from_account_id, 'to_account': self.to_account_id}

# ----------------------------------------------------------------------
# 6. Schemas
# ----------------------------------------------------------------------

class RegisterSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=3, max=80))
    email    = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=6))

class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True)

class CreateAccountSchema(Schema):
    account_type = fields.Str(validate=validate.OneOf(['checking','savings']), load_default='checking')
    currency     = fields.Str(validate=validate.Regexp(r'^[A-Z]{3}$'), load_default='USD')

class DepositSchema(Schema):
    account_id = fields.Int(required=True)
    amount     = fields.Decimal(required=True, validate=validate.Range(min=Decimal('0.01'), max=Decimal('100000')))

class WithdrawSchema(Schema):
    account_id = fields.Int(required=True)
    amount     = fields.Decimal(required=True, validate=validate.Range(min=Decimal('0.01'), max=Decimal('50000')))

class TransferSchema(Schema):
    from_account_id = fields.Int(required=True)
    to_account_id   = fields.Int(required=True)
    amount          = fields.Decimal(required=True, validate=validate.Range(min=Decimal('0.01'), max=Decimal('50000')))
    description     = fields.Str(validate=validate.Length(max=200), load_default='')

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
    ts  = datetime.now().strftime('%Y%m%d%H%M%S')
    rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'TXN-{ts}-{rnd}'

def handle_validation_error(error):
    return jsonify({'error': 'Validation Error', 'message': error.messages, 'status': 400}), 400

# ----------------------------------------------------------------------
# 8. JWT callbacks
# ----------------------------------------------------------------------

@jwt.user_identity_loader
def user_identity_lookup(user): return user.id

@jwt.user_lookup_loader
def user_lookup_callback(_h, d): return db.session.get(User, d["sub"])

@jwt.token_in_blocklist_loader
def check_if_token_revoked(h, p): return False

@jwt.expired_token_loader
def expired_token_callback(h, p):
    return jsonify({'error': 'Token Expired', 'status': 401}), 401

@jwt.invalid_token_loader
def invalid_token_callback(e):
    return jsonify({'error': 'Invalid Token', 'message': str(e), 'status': 422}), 422

@jwt.unauthorized_loader
def unauthorized_callback(e):
    return jsonify({'error': 'Unauthorized', 'status': 401}), 401

# ----------------------------------------------------------------------
# 9. Blueprints
# ----------------------------------------------------------------------

auth_bp         = Blueprint('auth', __name__)
accounts_bp     = Blueprint('accounts', __name__)
transactions_bp = Blueprint('transactions', __name__)

@auth_bp.route('/register', methods=['POST'])
@limiter.limit('5 per hour')
def register():
    data = request.get_json()
    try: validated = RegisterSchema().load(data)
    except ValidationError as err: return handle_validation_error(err)
    if User.query.filter_by(username=validated['username']).first():
        return jsonify({'error': 'Username already exists', 'status': 409}), 409
    if User.query.filter_by(email=validated['email']).first():
        return jsonify({'error': 'Email already registered', 'status': 409}), 409
    u = User(username=validated['username'], email=validated['email'])
    u.set_password(validated['password'])
    db.session.add(u); db.session.commit()
    return jsonify({'message': 'User created successfully',
                    'access_token': create_access_token(identity=u),
                    'refresh_token': create_refresh_token(identity=u),
                    'user': u.to_dict()}), 201

@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = request.get_json()
    try: validated = LoginSchema().load(data)
    except ValidationError as err: return handle_validation_error(err)
    u = User.query.filter_by(username=validated['username']).first()
    if not u or not u.check_password(validated['password']):
        return jsonify({'error': 'Invalid credentials', 'status': 401}), 401
    return jsonify({'access_token': create_access_token(identity=u),
                    'refresh_token': create_refresh_token(identity=u),
                    'user': u.to_dict()}), 200

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
    return jsonify({'accounts': [a.to_dict() for a in
        Account.query.filter_by(user_id=get_jwt_identity()).all()]}), 200

@accounts_bp.route('/<int:account_id>/balance', methods=['GET'])
@jwt_required()
def get_balance(account_id):
    a = Account.query.filter_by(id=account_id, user_id=get_jwt_identity()).first()
    if not a: return jsonify({'error': 'Account not found', 'status': 404}), 404
    return jsonify({'account_number': a.account_number, 'balance': str(a.balance), 'currency': a.currency}), 200

@accounts_bp.route('', methods=['POST'])
@jwt_required()
def create_account():
    data = request.get_json() or {}
    try: validated = CreateAccountSchema().load(data)
    except ValidationError as err: return handle_validation_error(err)
    a = Account(account_number=generate_account_number(),
                account_type=validated['account_type'],
                currency=validated['currency'],
                user_id=get_jwt_identity())
    db.session.add(a); db.session.commit()
    return jsonify({'message': 'Account created', 'account': a.to_dict()}), 201

@transactions_bp.route('/deposit', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def deposit():
    data = request.get_json()
    try: validated = DepositSchema().load(data)
    except ValidationError as err: return handle_validation_error(err)
    a = Account.query.filter_by(id=validated['account_id'], user_id=get_jwt_identity()).first()
    if not a: return jsonify({'error': 'Account not found', 'status': 404}), 404
    amt = validated['amount']
    a.balance += amt
    t = Transaction(amount=amt, type='deposit', status='completed',
                    reference=generate_transaction_reference(), to_account_id=a.id)
    db.session.add(t); db.session.commit()
    return jsonify({'message': 'Deposit successful', 'new_balance': str(a.balance), 'transaction_id': t.id}), 200

@transactions_bp.route('/withdraw', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def withdraw():
    data = request.get_json()
    try: validated = WithdrawSchema().load(data)
    except ValidationError as err: return handle_validation_error(err)
    a = Account.query.filter_by(id=validated['account_id'], user_id=get_jwt_identity()).first()
    if not a: return jsonify({'error': 'Account not found', 'status': 404}), 404
    amt = validated['amount']
    if a.balance < amt: return jsonify({'error': 'Insufficient funds', 'status': 400}), 400
    a.balance -= amt
    t = Transaction(amount=amt, type='withdrawal', status='completed',
                    reference=generate_transaction_reference(), from_account_id=a.id)
    db.session.add(t); db.session.commit()
    return jsonify({'message': 'Withdrawal successful', 'new_balance': str(a.balance), 'transaction_id': t.id}), 200

@transactions_bp.route('/transfer', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def transfer():
    data = request.get_json()
    try: validated = TransferSchema().load(data)
    except ValidationError as err: return handle_validation_error(err)
    src = Account.query.filter_by(id=validated['from_account_id'], user_id=get_jwt_identity()).first()
    if not src: return jsonify({'error': 'Source account not found', 'status': 404}), 404
    dst = Account.query.filter_by(id=validated['to_account_id']).first()
    if not dst: return jsonify({'error': 'Destination account not found', 'status': 404}), 404
    amt = validated['amount']
    if src.balance < amt: return jsonify({'error': 'Insufficient funds', 'status': 400}), 400
    src.balance -= amt; dst.balance += amt
    t = Transaction(amount=amt, type='transfer', status='completed',
                    description=validated['description'],
                    reference=generate_transaction_reference(),
                    from_account_id=src.id, to_account_id=dst.id)
    db.session.add(t); db.session.commit()
    return jsonify({'message': 'Transfer successful', 'source_balance': str(src.balance),
                    'destination_account': dst.account_number, 'transaction_id': t.id}), 200

@transactions_bp.route('/history', methods=['GET'])
@jwt_required()
def transaction_history():
    ids  = [a.id for a in Account.query.filter_by(user_id=get_jwt_identity()).all()]
    txns = Transaction.query.filter(
        db.or_(Transaction.from_account_id.in_(ids), Transaction.to_account_id.in_(ids))
    ).order_by(Transaction.created_at.desc()).limit(100).all()
    return jsonify({'transactions': [t.to_dict() for t in txns], 'count': len(txns)}), 200

# ----------------------------------------------------------------------
# 10. Run
# ----------------------------------------------------------------------

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    host  = os.environ.get('HOST', '0.0.0.0' if os.environ.get('FLASK_ENV') == 'production' else '127.0.0.1')
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host=host, port=port, debug=debug)
