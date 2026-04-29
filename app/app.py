"""
SecureBank — single-file Flask banking demo.

Run:
    pip install flask flask-sqlalchemy flask-jwt-extended flask-bcrypt \
                flask-talisman flask-limiter marshmallow prometheus-flask-exporter
    python app.py

Then open http://localhost:5000
"""
import os
import random
import string
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from flask_bcrypt import Bcrypt
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from marshmallow import Schema, fields, ValidationError, validate
from prometheus_flask_exporter import PrometheusMetrics


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-dev-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BCRYPT_LOG_ROUNDS = 12
    FORCE_HTTPS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    BCRYPT_LOG_ROUNDS = 4


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://user:pass@localhost:5432/securebank"
    )
    FORCE_HTTPS = True


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------
db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["1000/hour"])

# In-memory blocklist for logged-out tokens
TOKEN_BLOCKLIST = set()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    accounts = db.relationship("Account", backref="owner", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_active": self.is_active,
        }


class Account(db.Model):
    __tablename__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    account_type = db.Column(db.String(32), nullable=False, default="checking")
    balance = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(8), nullable=False, default="USD")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "account_number": self.account_number,
            "account_type": self.account_type,
            "balance": float(self.balance),
            "currency": self.currency,
            "user_id": self.user_id,
        }


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # deposit/withdrawal/transfer
    status = db.Column(db.String(20), nullable=False, default="completed")
    description = db.Column(db.String(255))
    from_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    to_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "reference": self.reference,
            "amount": float(self.amount),
            "type": self.type,
            "status": self.status,
            "description": self.description,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RegisterSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=3, max=64))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8, max=128))


class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True)


class AccountCreateSchema(Schema):
    account_type = fields.Str(load_default="checking",
                              validate=validate.OneOf(["checking", "savings"]))
    currency = fields.Str(load_default="USD",
                          validate=validate.OneOf(["USD", "EUR", "GBP"]))


class AmountSchema(Schema):
    account_id = fields.Int(required=True)
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))


class TransferSchema(Schema):
    from_account_id = fields.Int(required=True)
    to_account_id = fields.Int(required=True)
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    description = fields.Str(load_default="")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def gen_account_number():
    return "BANK-" + "".join(random.choices(string.digits, k=8))


def gen_reference():
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return "TXN-" + datetime.utcnow().strftime("%Y%m%d%H%M%S") + "-" + suffix


def err(msg, code=400):
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(CONFIG_MAP.get(config_name, DevelopmentConfig))

    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    csp = {
        "default-src": ["'self'"],
        "script-src": ["'self'", "'unsafe-inline'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'", "data:"],
        "connect-src": ["'self'"],
    }
    Talisman(
        app,
        force_https=app.config.get("FORCE_HTTPS", False),
        content_security_policy=csp,
        content_security_policy_nonce_in=[],
    )

    metrics = PrometheusMetrics(app)
    # FIX: skip metrics.info() during testing to avoid duplicate registration
    if not app.config.get("TESTING", False):
        metrics.info("securebank_app_info", "SecureBank application info", version="1.0.0")

    @jwt.token_in_blocklist_loader
    def check_blocklist(jwt_header, jwt_payload):
        return jwt_payload["jti"] in TOKEN_BLOCKLIST

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template_string(HTML)

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"})

    @app.route("/secure")
    def secure():
        return jsonify({"security": "enabled"})

    # -- Auth ---------------------------------------------------------------
    @app.route("/auth/register", methods=["POST"])
    @limiter.limit("5/hour")
    def register():
        try:
            data = RegisterSchema().load(request.get_json() or {})
        except ValidationError as e:
            return err(e.messages, 400)

        if User.query.filter_by(username=data["username"]).first():
            return err("Username already exists", 409)
        if User.query.filter_by(email=data["email"]).first():
            return err("Email already exists", 409)

        user = User(
            username=data["username"],
            email=data["email"],
            password_hash=bcrypt.generate_password_hash(data["password"]).decode(),
        )
        db.session.add(user)
        db.session.commit()

        access = create_access_token(identity=str(user.id))
        refresh = create_refresh_token(identity=str(user.id))
        return jsonify({
            "access_token": access,
            "refresh_token": refresh,
            "user": user.to_dict(),
        }), 201

    @app.route("/auth/login", methods=["POST"])
    @limiter.limit("10/minute")
    def login():
        try:
            data = LoginSchema().load(request.get_json() or {})
        except ValidationError as e:
            return err(e.messages, 400)

        user = User.query.filter_by(username=data["username"]).first()
        if not user or not bcrypt.check_password_hash(user.password_hash, data["password"]):
            return err("Invalid credentials", 401)
        if not user.is_active:
            return err("Account disabled", 403)

        access = create_access_token(identity=str(user.id))
        refresh = create_refresh_token(identity=str(user.id))
        return jsonify({
            "access_token": access,
            "refresh_token": refresh,
            "user": user.to_dict(),
        })

    @app.route("/auth/refresh", methods=["POST"])
    @jwt_required(refresh=True)
    def refresh():
        identity = get_jwt_identity()
        return jsonify({"access_token": create_access_token(identity=identity)})

    @app.route("/auth/logout", methods=["POST"])
    @jwt_required()
    def logout():
        TOKEN_BLOCKLIST.add(get_jwt()["jti"])
        return jsonify({"message": "Logged out"})

    # -- Accounts -----------------------------------------------------------
    @app.route("/accounts", methods=["GET"])
    @jwt_required()
    def list_accounts():
        uid = int(get_jwt_identity())
        accounts = Account.query.filter_by(user_id=uid).all()
        return jsonify({"accounts": [a.to_dict() for a in accounts]})

    @app.route("/accounts", methods=["POST"])
    @jwt_required()
    def create_account():
        uid = int(get_jwt_identity())
        try:
            data = AccountCreateSchema().load(request.get_json() or {})
        except ValidationError as e:
            return err(e.messages, 400)

        # ensure unique account number
        for _ in range(5):
            number = gen_account_number()
            if not Account.query.filter_by(account_number=number).first():
                break

        acct = Account(
            account_number=number,
            account_type=data["account_type"],
            currency=data["currency"],
            user_id=uid,
            balance=0,
        )
        db.session.add(acct)
        db.session.commit()
        return jsonify({"account": acct.to_dict()}), 201

    @app.route("/accounts/<int:account_id>/balance", methods=["GET"])
    @jwt_required()
    def get_balance(account_id):
        uid = int(get_jwt_identity())
        acct = Account.query.filter_by(id=account_id, user_id=uid).first()
        if not acct:
            return err("Account not found", 404)
        return jsonify({"balance": float(acct.balance), "currency": acct.currency})

    # -- Transactions -------------------------------------------------------
    @app.route("/transactions/deposit", methods=["POST"])
    @jwt_required()
    @limiter.limit("30/minute")
    def deposit():
        uid = int(get_jwt_identity())
        try:
            data = AmountSchema().load(request.get_json() or {})
        except ValidationError as e:
            return err(e.messages, 400)

        acct = Account.query.filter_by(id=data["account_id"], user_id=uid).first()
        if not acct:
            return err("Account not found", 404)

        acct.balance = float(acct.balance) + data["amount"]
        tx = Transaction(
            reference=gen_reference(),
            amount=data["amount"],
            type="deposit",
            status="completed",
            description="Deposit",
            to_account_id=acct.id,
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"transaction": tx.to_dict(), "account": acct.to_dict()}), 201

    @app.route("/transactions/withdraw", methods=["POST"])
    @jwt_required()
    @limiter.limit("30/minute")
    def withdraw():
        uid = int(get_jwt_identity())
        try:
            data = AmountSchema().load(request.get_json() or {})
        except ValidationError as e:
            return err(e.messages, 400)

        acct = Account.query.filter_by(id=data["account_id"], user_id=uid).first()
        if not acct:
            return err("Account not found", 404)
        if float(acct.balance) < data["amount"]:
            return err("Insufficient funds", 400)

        acct.balance = float(acct.balance) - data["amount"]
        tx = Transaction(
            reference=gen_reference(),
            amount=data["amount"],
            type="withdrawal",
            status="completed",
            description="Withdrawal",
            from_account_id=acct.id,
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"transaction": tx.to_dict(), "account": acct.to_dict()}), 201

    @app.route("/transactions/transfer", methods=["POST"])
    @jwt_required()
    @limiter.limit("30/minute")
    def transfer():
        uid = int(get_jwt_identity())
        try:
            data = TransferSchema().load(request.get_json() or {})
        except ValidationError as e:
            return err(e.messages, 400)

        if data["from_account_id"] == data["to_account_id"]:
            return err("Cannot transfer to the same account", 400)

        src = Account.query.filter_by(id=data["from_account_id"], user_id=uid).first()
        if not src:
            return err("Source account not found", 404)
        dst = Account.query.filter_by(id=data["to_account_id"]).first()
        if not dst:
            return err("Destination account not found", 404)
        if float(src.balance) < data["amount"]:
            return err("Insufficient funds", 400)

        src.balance = float(src.balance) - data["amount"]
        dst.balance = float(dst.balance) + data["amount"]
        tx = Transaction(
            reference=gen_reference(),
            amount=data["amount"],
            type="transfer",
            status="completed",
            description=data.get("description") or "Transfer",
            from_account_id=src.id,
            to_account_id=dst.id,
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"transaction": tx.to_dict()}), 201

    @app.route("/transactions/history", methods=["GET"])
    @jwt_required()
    def history():
        uid = int(get_jwt_identity())
        account_ids = [a.id for a in Account.query.filter_by(user_id=uid).all()]
        if not account_ids:
            return jsonify({"transactions": []})
        txs = (
            Transaction.query
            .filter(
                (Transaction.from_account_id.in_(account_ids)) |
                (Transaction.to_account_id.in_(account_ids))
            )
            .order_by(Transaction.created_at.desc())
            .limit(100)
            .all()
        )
        return jsonify({"transactions": [t.to_dict() for t in txs]})

    # -----------------------------------------------------------------------
    @app.errorhandler(429)
    def ratelimit(e):
        return jsonify({"error": "Rate limit exceeded", "detail": str(e.description)}), 429

    with app.app_context():
        db.create_all()

    return app


# ---------------------------------------------------------------------------
# Front-end (single-page HTML/CSS/JS)
# ---------------------------------------------------------------------------
HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>SecureBank — Banking made simple</title>
<style>
:root{
  --navy:#0d1b2a; --blue:#1565c0; --blue-light:#1976d2; --accent:#4fc3f7;
  --green:#2e7d32; --orange:#e65100; --red:#c62828; --yellow:#f9a825;
  --bg:#f4f6fb; --card:#ffffff; --border:#e0e7ef; --text:#1a1a2e;
  --muted:#6b7280; --shadow:0 2px 12px rgba(0,0,0,.08);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);
  font-family:'Segoe UI',system-ui,-apple-system,sans-serif;line-height:1.5}
a{color:inherit;text-decoration:none}
button{font-family:inherit;cursor:pointer;border:none;background:none}

/* Navbar */
.nav{position:sticky;top:0;z-index:50;height:64px;background:var(--navy);
  color:#fff;display:flex;align-items:center;padding:0 2rem;
  box-shadow:0 2px 8px rgba(0,0,0,.2)}
.nav .brand{font-weight:700;font-size:1.25rem;letter-spacing:.5px;display:flex;
  align-items:center;gap:.5rem}
.nav .brand .dot{width:10px;height:10px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 12px var(--accent)}
.nav .links{display:flex;gap:1.5rem;margin-left:2.5rem}
.nav .links a{opacity:.85;font-size:.95rem;transition:opacity .2s}
.nav .links a:hover{opacity:1}
.nav .spacer{flex:1}
.nav .auth-area{display:flex;gap:.6rem;align-items:center}
.nav .user{opacity:.9;font-size:.9rem;margin-right:.4rem}
.btn{padding:.55rem 1.1rem;border-radius:8px;font-weight:600;font-size:.9rem;
  transition:transform .15s, box-shadow .2s, background .2s, color .2s;
  display:inline-flex;align-items:center;gap:.4rem}
.btn-ghost{color:#fff;background:transparent;border:1px solid rgba(255,255,255,.25)}
.btn-ghost:hover{background:rgba(255,255,255,.08)}
.btn-primary{background:var(--blue);color:#fff}
.btn-primary:hover{background:var(--blue-light)}
.btn-accent{background:var(--accent);color:var(--navy)}
.btn-accent:hover{background:#81d4fa}
.btn-outline{background:#fff;border:1.5px solid var(--border);color:var(--text)}
.btn-outline:hover{border-color:var(--blue);color:var(--blue)}
.btn-danger{background:var(--red);color:#fff}
.btn-danger:hover{filter:brightness(1.1)}
.btn-cta{padding:.95rem 1.8rem;border-radius:30px;font-size:1rem;font-weight:600}
.btn-cta.btn-primary:hover{transform:translateY(-2px);
  box-shadow:0 12px 28px -8px rgba(21,101,192,.6),0 0 24px rgba(79,195,247,.35)}
.btn-block{width:100%;justify-content:center;padding:.7rem 1rem;border-radius:8px}

/* Hero */
.hero{background:linear-gradient(135deg,#0d1b2a 0%,#1565c0 100%);color:#fff;
  padding:5rem 2rem;text-align:center;position:relative;overflow:hidden}
.hero::after{content:"";position:absolute;inset:0;
  background:radial-gradient(circle at 80% 20%,rgba(79,195,247,.2),transparent 50%);
  pointer-events:none}
.hero h1{font-size:clamp(2rem,5vw,3.6rem);margin:0 0 1rem;font-weight:700;
  letter-spacing:-.5px}
.hero p{font-size:clamp(1rem,2vw,1.25rem);opacity:.9;max-width:640px;
  margin:0 auto 2rem}
.hero .cta{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;
  position:relative;z-index:1}

/* Ticker */
.ticker{background:#0a1422;color:#e6f2ff;padding:.7rem 1rem;display:flex;gap:2rem;
  overflow-x:auto;font-size:.88rem;border-bottom:1px solid rgba(255,255,255,.05);
  white-space:nowrap;scrollbar-width:none}
.ticker::-webkit-scrollbar{display:none}
.ticker .item{display:inline-flex;align-items:center;gap:.45rem}
.ticker .sym{opacity:.7;font-weight:600;letter-spacing:.5px}
.ticker .price{font-variant-numeric:tabular-nums}
.ticker .up{color:#66bb6a}
.ticker .down{color:#ef5350}

/* Sections */
.section{padding:4rem 2rem;max-width:1200px;margin:0 auto}
.section h2{font-size:clamp(1.6rem,3vw,2.2rem);margin:0 0 .5rem;text-align:center}
.section .lead{color:var(--muted);text-align:center;margin:0 auto 3rem;
  max-width:560px}

/* Features */
.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
  gap:1.25rem}
.feature{background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:1.6rem;box-shadow:var(--shadow);transition:transform .25s, box-shadow .25s}
.feature:hover{transform:translateY(-4px);box-shadow:0 12px 28px rgba(13,27,42,.12)}
.feature .ico{font-size:2rem;margin-bottom:.7rem}
.feature h3{margin:.2rem 0 .4rem;font-size:1.1rem}
.feature p{margin:0;color:var(--muted);font-size:.93rem}

/* Stats */
.stats{background:linear-gradient(135deg,var(--blue) 0%,var(--blue-light) 100%);
  color:#fff;padding:3rem 2rem;text-align:center}
.stats .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:2rem;max-width:1100px;margin:0 auto}
.stats .num{font-size:2rem;font-weight:700}
.stats .lbl{opacity:.85;font-size:.95rem;margin-top:.3rem}

/* How it works */
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:1.25rem}
.step{background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:1.6rem;box-shadow:var(--shadow);position:relative}
.step .n{width:34px;height:34px;border-radius:50%;background:var(--blue);color:#fff;
  display:inline-flex;align-items:center;justify-content:center;font-weight:700;
  margin-bottom:.7rem}
.step h4{margin:.2rem 0 .4rem}
.step p{margin:0;color:var(--muted);font-size:.93rem}

/* CTA banner */
.cta-banner{background:linear-gradient(135deg,#0d1b2a 0%,#1565c0 100%);color:#fff;
  padding:3.5rem 2rem;text-align:center}
.cta-banner h2{margin:0 0 1.2rem;font-size:clamp(1.6rem,3vw,2.2rem)}

/* Footer */
.footer{background:#0a1422;color:#a8b8c9;padding:1.8rem 2rem;text-align:center;
  font-size:.88rem}

/* Modal */
.backdrop{position:fixed;inset:0;background:rgba(10,20,34,.55);backdrop-filter:blur(3px);
  display:none;align-items:center;justify-content:center;z-index:100;padding:1rem}
.backdrop.show{display:flex}
.modal{background:#fff;border-radius:14px;box-shadow:0 24px 60px rgba(0,0,0,.35);
  width:100%;max-width:420px;overflow:hidden;animation:pop .2s ease-out}
@keyframes pop{from{transform:scale(.95);opacity:0}to{transform:scale(1);opacity:1}}
.modal .head{padding:1.4rem 1.6rem 0}
.modal .head h3{margin:0 0 1rem;font-size:1.3rem}
.tabs{display:flex;border-bottom:1px solid var(--border)}
.tabs .tab{flex:1;padding:.85rem;text-align:center;font-weight:600;color:var(--muted);
  border-bottom:2px solid transparent;cursor:pointer}
.tabs .tab.active{color:var(--blue);border-color:var(--blue)}
.modal .body{padding:1.4rem 1.6rem}
.modal .actions{display:flex;gap:.6rem;justify-content:flex-end;
  padding:0 1.6rem 1.4rem}
.field{margin-bottom:.9rem}
.field label{display:block;font-size:.85rem;font-weight:600;margin-bottom:.35rem;
  color:#374151}
.field input,.field select{width:100%;padding:.65rem .8rem;border:1.5px solid var(--border);
  border-radius:8px;font-size:.95rem;font-family:inherit;background:#fff;
  transition:border-color .15s, box-shadow .15s}
.field input:focus,.field select:focus{outline:none;border-color:var(--blue);
  box-shadow:0 0 0 3px rgba(21,101,192,.15)}
.alert{padding:.7rem .9rem;border-radius:8px;font-size:.88rem;margin-bottom:.9rem}
.alert.error{background:#fdecea;color:#b71c1c;border:1px solid #f5c2bf}
.alert.success{background:#e8f5e9;color:#1b5e20;border:1px solid #b9dfbb}
.alert.hidden{display:none}

/* Dashboard */
.dashboard{display:none;padding:2rem;max-width:1280px;margin:0 auto}
.dashboard.show{display:block}
.dash-head{margin-bottom:1.5rem}
.dash-head h1{margin:0 0 .25rem;font-size:1.8rem}
.dash-head p{margin:0;color:var(--muted)}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:1rem;margin-bottom:1.5rem}
.sum-card{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:1.2rem;box-shadow:var(--shadow)}
.sum-card .lbl{color:var(--muted);font-size:.85rem;margin-bottom:.4rem}
.sum-card .val{font-size:1.6rem;font-weight:700}
.cols{display:grid;grid-template-columns:1.2fr 1fr;gap:1.25rem;margin-bottom:1.5rem}
@media(max-width:700px){.cols{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--border);border-radius:12px;
  box-shadow:var(--shadow);padding:1.4rem}
.panel h3{margin:0 0 1rem;font-size:1.1rem}
.acct-list{display:flex;flex-direction:column;gap:.85rem;margin-bottom:1rem}
.acct{background:linear-gradient(135deg,var(--blue) 0%,var(--blue-light) 100%);
  color:#fff;border-radius:12px;padding:1.1rem 1.3rem;
  box-shadow:0 6px 18px rgba(21,101,192,.25)}
.acct .num{font-family:'Courier New',monospace;font-size:.92rem;opacity:.85;
  letter-spacing:1px}
.acct .type{text-transform:capitalize;font-size:.8rem;opacity:.85;margin-top:.2rem}
.acct .bal{font-size:1.7rem;font-weight:700;margin-top:.6rem;
  font-variant-numeric:tabular-nums}
.acct .cur{font-size:.95rem;opacity:.85;margin-left:.3rem;font-weight:500}
.action-tabs{display:flex;border-bottom:1px solid var(--border);margin-bottom:1rem}
.action-tabs .tab{flex:1;padding:.7rem;text-align:center;font-weight:600;
  color:var(--muted);border-bottom:2px solid transparent;cursor:pointer;font-size:.9rem}
.action-tabs .tab.active{color:var(--blue);border-color:var(--blue)}
.action-form{display:none}
.action-form.active{display:block}
.tx-table{width:100%;border-collapse:collapse;font-size:.9rem}
.tx-table th,.tx-table td{padding:.7rem .6rem;text-align:left;
  border-bottom:1px solid var(--border)}
.tx-table th{color:var(--muted);font-weight:600;font-size:.78rem;
  text-transform:uppercase;letter-spacing:.5px}
.tx-table td.ref{font-family:'Courier New',monospace;font-size:.82rem;color:var(--muted)}
.badge{display:inline-block;padding:.22rem .55rem;border-radius:12px;font-size:.75rem;
  font-weight:600;text-transform:capitalize}
.badge.deposit{background:#e8f5e9;color:var(--green)}
.badge.withdrawal{background:#fff3e0;color:var(--orange)}
.badge.transfer{background:#e3f2fd;color:var(--blue)}
.badge.completed{background:#e8f5e9;color:var(--green)}
.badge.pending{background:#fffde7;color:var(--yellow)}
.badge.failed{background:#fdecea;color:var(--red)}
.empty{text-align:center;color:var(--muted);padding:2rem}
</style>
</head>
<body>

<!-- Public site (landing) -->
<div id="site">
  <nav class="nav">
    <div class="brand"><span class="dot"></span> SecureBank</div>
    <div class="links">
      <a href="#home">Home</a>
      <a href="#features">Features</a>
      <a href="#how">How it works</a>
    </div>
    <div class="spacer"></div>
    <div class="auth-area" id="authArea">
      <button class="btn btn-ghost" onclick="openAuth('login')">Log in</button>
      <button class="btn btn-accent" onclick="openAuth('register')">Sign up</button>
    </div>
  </nav>

  <section class="hero" id="home">
    <h1>Banking made simple and secure</h1>
    <p>Open accounts, transfer money, and track every transaction in real time —
       backed by bank-grade security and a modern DevSecOps pipeline.</p>
    <div class="cta">
      <button class="btn btn-cta btn-primary" onclick="openAuth('register')">
        Get started — it's free
      </button>
      <button class="btn btn-cta btn-outline"
              onclick="document.getElementById('features').scrollIntoView({behavior:'smooth'})">
        Learn more
      </button>
    </div>
  </section>

  <div class="ticker" id="ticker"></div>

  <section class="section" id="features">
    <h2>Everything you need to bank smarter</h2>
    <p class="lead">A complete banking experience built on a secure, observable, cloud-native platform.</p>
    <div class="features">
      <div class="feature"><div class="ico">🔒</div><h3>Bank-grade security</h3>
        <p>JWT auth, bcrypt password hashing, Talisman security headers, and a strict CSP.</p></div>
      <div class="feature"><div class="ico">⚡</div><h3>Instant transfers</h3>
        <p>Move funds between your accounts and to other users in milliseconds.</p></div>
      <div class="feature"><div class="ico">📊</div><h3>Transaction history</h3>
        <p>Every deposit, withdrawal, and transfer logged with a unique reference.</p></div>
      <div class="feature"><div class="ico">💳</div><h3>Multiple accounts</h3>
        <p>Open as many checking and savings accounts as you need — in USD, EUR or GBP.</p></div>
      <div class="feature"><div class="ico">📈</div><h3>Live monitoring</h3>
        <p>Prometheus metrics out of the box — every request observed and measured.</p></div>
      <div class="feature"><div class="ico">🛡️</div><h3>DevSecOps pipeline</h3>
        <p>Built and deployed with Trivy scanning, Kyverno policies and Falco runtime defense.</p></div>
    </div>
  </section>

  <section class="stats">
    <div class="grid">
      <div><div class="num">99.9%</div><div class="lbl">Uptime SLA</div></div>
      <div><div class="num">&lt;50ms</div><div class="lbl">Median response</div></div>
      <div><div class="num">AES-256</div><div class="lbl">Encryption at rest</div></div>
      <div><div class="num">24/7</div><div class="lbl">Monitoring</div></div>
    </div>
  </section>

  <section class="section" id="how">
    <h2>How it works</h2>
    <p class="lead">From sign-up to your first transfer in under a minute.</p>
    <div class="steps">
      <div class="step"><div class="n">1</div><h4>Create an account</h4>
        <p>Pick a username, share an email and a strong password. That's it.</p></div>
      <div class="step"><div class="n">2</div><h4>Open a bank account</h4>
        <p>Choose checking or savings, and your preferred currency.</p></div>
      <div class="step"><div class="n">3</div><h4>Deposit funds</h4>
        <p>Top up your balance instantly, anytime.</p></div>
      <div class="step"><div class="n">4</div><h4>Transfer & track</h4>
        <p>Send money and follow every move in your live transaction history.</p></div>
    </div>
  </section>

  <section class="cta-banner">
    <h2>Ready to get started?</h2>
    <button class="btn btn-cta btn-accent" onclick="openAuth('register')">
      Create your free account
    </button>
  </section>

  <footer class="footer">
    SecureBank — DevSecOps demo • Deployed on Kubernetes • Protected by Kyverno + Falco + Trivy
  </footer>
</div>

<!-- Dashboard -->
<div id="dashboard" class="dashboard">
  <div class="dash-head">
    <h1>Dashboard</h1>
    <p>Welcome back, <span id="dashUser"></span></p>
  </div>

  <div class="summary">
    <div class="sum-card"><div class="lbl">Total Balance</div>
      <div class="val" id="sumBalance">$0.00</div></div>
    <div class="sum-card"><div class="lbl">Accounts</div>
      <div class="val" id="sumAccounts">0</div></div>
    <div class="sum-card"><div class="lbl">Transactions</div>
      <div class="val" id="sumTx">0</div></div>
  </div>

  <div class="cols">
    <div class="panel">
      <h3>Your accounts</h3>
      <div class="acct-list" id="acctList"></div>
      <button class="btn btn-outline btn-block" onclick="openNewAccount()">
        + Open another account
      </button>
    </div>

    <div class="panel">
      <h3>Quick Actions</h3>
      <div class="action-tabs">
        <div class="tab active" data-act="deposit" onclick="switchAction('deposit')">Deposit</div>
        <div class="tab" data-act="withdraw" onclick="switchAction('withdraw')">Withdraw</div>
        <div class="tab" data-act="transfer" onclick="switchAction('transfer')">Transfer</div>
      </div>
      <div id="actionAlert" class="alert hidden"></div>

      <form class="action-form active" data-form="deposit" onsubmit="return doDeposit(event)">
        <div class="field"><label>Account</label>
          <select id="depAcct" required></select></div>
        <div class="field"><label>Amount</label>
          <input id="depAmt" type="number" step="0.01" min="0.01" required></div>
        <button class="btn btn-primary btn-block" type="submit">Deposit</button>
      </form>

      <form class="action-form" data-form="withdraw" onsubmit="return doWithdraw(event)">
        <div class="field"><label>Account</label>
          <select id="wAcct" required></select></div>
        <div class="field"><label>Amount</label>
          <input id="wAmt" type="number" step="0.01" min="0.01" required></div>
        <button class="btn btn-primary btn-block" type="submit">Withdraw</button>
      </form>

      <form class="action-form" data-form="transfer" onsubmit="return doTransfer(event)">
        <div class="field"><label>From</label>
          <select id="tFrom" required></select></div>
        <div class="field"><label>To account ID</label>
          <input id="tTo" type="number" min="1" required placeholder="Destination account id"></div>
        <div class="field"><label>Amount</label>
          <input id="tAmt" type="number" step="0.01" min="0.01" required></div>
        <div class="field"><label>Description</label>
          <input id="tDesc" type="text" placeholder="Optional"></div>
        <button class="btn btn-primary btn-block" type="submit">Transfer</button>
      </form>
    </div>
  </div>

  <div class="panel">
    <h3>Transaction history</h3>
    <div id="txWrap">
      <table class="tx-table" id="txTable">
        <thead><tr><th>Reference</th><th>Type</th><th>Amount</th>
          <th>Status</th><th>Date</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<!-- Auth modal -->
<div class="backdrop" id="authBackdrop" onclick="if(event.target===this)closeAuth()">
  <div class="modal">
    <div class="head"><h3>Welcome to SecureBank</h3></div>
    <div class="tabs">
      <div class="tab active" data-auth="login" onclick="switchAuth('login')">Log in</div>
      <div class="tab" data-auth="register" onclick="switchAuth('register')">Sign up</div>
    </div>
    <div class="body">
      <div id="authAlert" class="alert hidden"></div>

      <form id="loginForm" onsubmit="return doLogin(event)">
        <div class="field"><label>Username</label>
          <input id="liUser" required autocomplete="username"></div>
        <div class="field"><label>Password</label>
          <input id="liPass" type="password" required autocomplete="current-password"></div>
        <button class="btn btn-primary btn-block" type="submit">Sign in</button>
      </form>

      <form id="registerForm" style="display:none" onsubmit="return doRegister(event)">
        <div class="field"><label>Username</label>
          <input id="rUser" required minlength="3"></div>
        <div class="field"><label>Email</label>
          <input id="rEmail" type="email" required></div>
        <div class="field"><label>Password</label>
          <input id="rPass" type="password" required minlength="8"
                 placeholder="At least 8 characters"></div>
        <button class="btn btn-primary btn-block" type="submit">Create account</button>
      </form>
    </div>
    <div class="actions">
      <button class="btn btn-outline" onclick="closeAuth()">Cancel</button>
    </div>
  </div>
</div>

<!-- New account modal -->
<div class="backdrop" id="acctBackdrop" onclick="if(event.target===this)closeNewAccount()">
  <div class="modal">
    <div class="head"><h3>Open a new account</h3></div>
    <div class="body">
      <div id="acctAlert" class="alert hidden"></div>
      <form onsubmit="return doCreateAccount(event)">
        <div class="field"><label>Account type</label>
          <select id="naType"><option value="checking">Checking</option>
            <option value="savings">Savings</option></select></div>
        <div class="field"><label>Currency</label>
          <select id="naCur"><option>USD</option><option>EUR</option><option>GBP</option></select></div>
        <button class="btn btn-primary btn-block" type="submit">Open account</button>
      </form>
    </div>
    <div class="actions">
      <button class="btn btn-outline" onclick="closeNewAccount()">Cancel</button>
    </div>
  </div>
</div>

<script>
// ---------- State ----------
const TOKEN_KEY = 'sb_token';
let user = null;
let accounts = [];
let transactions = [];

// ---------- Helpers ----------
function token(){ return localStorage.getItem(TOKEN_KEY); }
function setToken(t){ localStorage.setItem(TOKEN_KEY, t); }
function clearToken(){ localStorage.removeItem(TOKEN_KEY); }

async function api(path, opts={}){
  const headers = {'Content-Type':'application/json', ...(opts.headers||{})};
  const t = token();
  if(t) headers['Authorization'] = 'Bearer '+t;
  const res = await fetch(path, {...opts, headers});
  let data = null;
  try{ data = await res.json(); }catch(e){}
  if(!res.ok){
    const msg = (data && (data.error || data.message)) || ('Request failed ('+res.status+')');
    const e = new Error(typeof msg==='string'?msg:JSON.stringify(msg));
    e.status = res.status;
    throw e;
  }
  return data;
}

function showAlert(id, msg, type='error'){
  const el = document.getElementById(id);
  el.textContent = msg;
  el.className = 'alert '+type;
}
function hideAlert(id){
  const el = document.getElementById(id);
  el.className = 'alert hidden';
}

function fmtMoney(n, cur='USD'){
  const sym = {USD:'$',EUR:'€',GBP:'£'}[cur] || '';
  return sym + Number(n).toLocaleString(undefined,{minimumFractionDigits:2, maximumFractionDigits:2});
}

// ---------- Auth modal ----------
function openAuth(tab){
  document.getElementById('authBackdrop').classList.add('show');
  switchAuth(tab||'login');
  hideAlert('authAlert');
  setTimeout(()=>{
    const el = document.getElementById(tab==='register'?'rUser':'liUser');
    if(el) el.focus();
  },50);
}
function closeAuth(){ document.getElementById('authBackdrop').classList.remove('show'); }
function switchAuth(which){
  document.querySelectorAll('.tabs .tab[data-auth]').forEach(t=>{
    t.classList.toggle('active', t.dataset.auth===which);
  });
  document.getElementById('loginForm').style.display = which==='login'?'block':'none';
  document.getElementById('registerForm').style.display = which==='register'?'block':'none';
  hideAlert('authAlert');
}

async function doLogin(e){
  e.preventDefault();
  hideAlert('authAlert');
  try{
    const data = await api('/auth/login', {method:'POST', body: JSON.stringify({
      username: liUser.value, password: liPass.value
    })});
    setToken(data.access_token);
    user = data.user;
    closeAuth();
    await enterDashboard();
  }catch(err){ showAlert('authAlert', err.message); }
  return false;
}
async function doRegister(e){
  e.preventDefault();
  hideAlert('authAlert');
  try{
    const data = await api('/auth/register', {method:'POST', body: JSON.stringify({
      username: rUser.value, email: rEmail.value, password: rPass.value
    })});
    setToken(data.access_token);
    user = data.user;
    closeAuth();
    await enterDashboard();
  }catch(err){ showAlert('authAlert', err.message); }
  return false;
}

async function doLogout(){
  try{ await api('/auth/logout', {method:'POST'}); }catch(e){}
  clearToken();
  user = null; accounts = []; transactions = [];
  document.getElementById('site').style.display = '';
  document.getElementById('dashboard').classList.remove('show');
  renderAuthArea();
}

// ---------- Nav ----------
function renderAuthArea(){
  const el = document.getElementById('authArea');
  if(user){
    el.innerHTML = `
      <span class="user">Hi, ${user.username}</span>
      <button class="btn btn-ghost" onclick="scrollDashboard()">Dashboard</button>
      <button class="btn btn-danger" onclick="doLogout()">Log out</button>`;
  }else{
    el.innerHTML = `
      <button class="btn btn-ghost" onclick="openAuth('login')">Log in</button>
      <button class="btn btn-accent" onclick="openAuth('register')">Sign up</button>`;
  }
}
function scrollDashboard(){
  document.getElementById('dashboard').scrollIntoView({behavior:'smooth'});
}

// ---------- Dashboard ----------
async function enterDashboard(){
  document.getElementById('site').style.display = 'none';
  document.getElementById('dashboard').classList.add('show');
  document.getElementById('dashUser').textContent = user ? user.username : '';
  renderAuthArea();
  await reloadAll();
}

async function reloadAll(){
  await Promise.all([reloadAccounts(), reloadTx()]);
  renderSummary();
}

async function reloadAccounts(){
  const data = await api('/accounts');
  accounts = data.accounts || [];
  renderAccounts();
  renderAccountSelectors();
}
async function reloadTx(){
  const data = await api('/transactions/history');
  transactions = data.transactions || [];
  renderTx();
}

function renderSummary(){
  const total = accounts.reduce((s,a)=>s+Number(a.balance||0),0);
  document.getElementById('sumBalance').textContent =
    fmtMoney(total, accounts[0]?.currency || 'USD');
  document.getElementById('sumAccounts').textContent = accounts.length;
  document.getElementById('sumTx').textContent = transactions.length;
}

function renderAccounts(){
  const el = document.getElementById('acctList');
  if(!accounts.length){
    el.innerHTML = '<div class="empty">No accounts yet. Open one to get started.</div>';
    return;
  }
  el.innerHTML = accounts.map(a=>`
    <div class="acct">
      <div class="num">${a.account_number}</div>
      <div class="type">${a.account_type} • #${a.id}</div>
      <div class="bal">${fmtMoney(a.balance,a.currency)}<span class="cur">${a.currency}</span></div>
    </div>`).join('');
}
function renderAccountSelectors(){
  const opts = accounts.map(a=>
    `<option value="${a.id}">${a.account_number} (${a.currency} ${fmtMoney(a.balance,a.currency)})</option>`
  ).join('');
  ['depAcct','wAcct','tFrom'].forEach(id=>{
    const sel = document.getElementById(id);
    if(sel) sel.innerHTML = opts || '<option value="">No accounts</option>';
  });
}
function renderTx(){
  const tbody = document.querySelector('#txTable tbody');
  if(!transactions.length){
    tbody.innerHTML = '<tr><td colspan="5" class="empty">No transactions yet.</td></tr>';
    return;
  }
  tbody.innerHTML = transactions.map(t=>{
    const d = t.created_at ? new Date(t.created_at).toLocaleString() : '';
    return `<tr>
      <td class="ref">${t.reference}</td>
      <td><span class="badge ${t.type}">${t.type}</span></td>
      <td>${fmtMoney(t.amount)}</td>
      <td><span class="badge ${t.status}">${t.status}</span></td>
      <td>${d}</td>
    </tr>`;
  }).join('');
}

// ---------- Quick actions ----------
function switchAction(which){
  document.querySelectorAll('.action-tabs .tab').forEach(t=>{
    t.classList.toggle('active', t.dataset.act===which);
  });
  document.querySelectorAll('.action-form').forEach(f=>{
    f.classList.toggle('active', f.dataset.form===which);
  });
  hideAlert('actionAlert');
}
async function withAction(fn){
  hideAlert('actionAlert');
  try{
    const msg = await fn();
    showAlert('actionAlert', msg, 'success');
    await reloadAll();
  }catch(err){
    showAlert('actionAlert', err.message);
  }
  return false;
}
function doDeposit(e){ e.preventDefault(); return withAction(async()=>{
  await api('/transactions/deposit',{method:'POST',body:JSON.stringify({
    account_id: Number(depAcct.value), amount: Number(depAmt.value)})});
  depAmt.value='';
  return 'Deposit completed.';
});}
function doWithdraw(e){ e.preventDefault(); return withAction(async()=>{
  await api('/transactions/withdraw',{method:'POST',body:JSON.stringify({
    account_id: Number(wAcct.value), amount: Number(wAmt.value)})});
  wAmt.value='';
  return 'Withdrawal completed.';
});}
function doTransfer(e){ e.preventDefault(); return withAction(async()=>{
  await api('/transactions/transfer',{method:'POST',body:JSON.stringify({
    from_account_id: Number(tFrom.value),
    to_account_id: Number(tTo.value),
    amount: Number(tAmt.value),
    description: tDesc.value
  })});
  tAmt.value=''; tDesc.value='';
  return 'Transfer completed.';
});}

// ---------- New account ----------
function openNewAccount(){
  document.getElementById('acctBackdrop').classList.add('show');
  hideAlert('acctAlert');
}
function closeNewAccount(){
  document.getElementById('acctBackdrop').classList.remove('show');
}
async function doCreateAccount(e){
  e.preventDefault();
  hideAlert('acctAlert');
  try{
    await api('/accounts',{method:'POST', body:JSON.stringify({
      account_type: naType.value, currency: naCur.value
    })});
    closeNewAccount();
    await reloadAll();
  }catch(err){ showAlert('acctAlert', err.message); }
  return false;
}

// ---------- Live ticker ----------
const symbols = [
  {sym:'EUR/USD', price:1.0825, dec:4},
  {sym:'GBP/USD', price:1.2640, dec:4},
  {sym:'USD/JPY', price:152.30, dec:2},
  {sym:'BTC/USD', price:68420, dec:0},
  {sym:'ETH/USD', price:3520, dec:2},
  {sym:'XAU (Gold)', price:2335.40, dec:2}
];
function renderTicker(){
  const el = document.getElementById('ticker');
  el.innerHTML = symbols.map(s=>{
    const dir = s.last && s.price>=s.last ? 'up' : 'down';
    const arrow = dir==='up' ? '▲' : '▼';
    return `<div class="item"><span class="sym">${s.sym}</span>
      <span class="price">${s.price.toLocaleString(undefined,{minimumFractionDigits:s.dec,maximumFractionDigits:s.dec})}</span>
      <span class="${dir}">${arrow}</span></div>`;
  }).join('');
}
function jitterTicker(){
  symbols.forEach(s=>{
    s.last = s.price;
    const pct = (Math.random()-0.5) * 0.004;
    s.price = Math.max(0.0001, s.price * (1+pct));
  });
  renderTicker();
}
renderTicker();
setInterval(jitterTicker, 3000);

// ---------- Boot ----------
(async function init(){
  // Enter key on auth forms is native; backdrop close is handled inline.
  if(token()){
    try{
      const data = await api('/accounts');
      accounts = data.accounts || [];
      // we don't have a /me endpoint — derive a username from token-less state
      // Try to fetch tx; if token bad, both will throw 401 first.
      const tx = await api('/transactions/history');
      transactions = tx.transactions || [];
      // No /me — keep username unknown but show "Account"
      user = user || {username:'Account'};
      await enterDashboard();
    }catch(err){
      if(err.status === 401) clearToken();
      renderAuthArea();
    }
  }else{
    renderAuthArea();
  }
})();
</script>
</body>
</html>
"""


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
