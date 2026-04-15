# app/app.py
"""
Production banking backend with JWT authentication, PostgreSQL,
and core banking operations (deposit, withdraw, transfer).
Single‑file version – all blueprints defined inline.
"""
import os
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask, jsonify, request, g, Blueprint
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

# ----------------------------------------------------------------------
# 1. App Configuration
# ----------------------------------------------------------------------

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-dev-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.environ.get('JWT_ACCESS_EXPIRES', 15)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get('JWT_REFRESH_EXPIRES', 7)))
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://bankuser:bankpass@localhost:5432/bankdb'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }

    # Rate limiting
    RATELIMIT_DEFAULT = "200 per day;50 per hour;5 per minute"
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True

    # Logging
    LOG_LEVEL = logging.INFO


class DevelopmentConfig(Config):
    DEBUG = True
    RATELIMIT_ENABLED = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}   # SQLite does not support pool options
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
# 2. App Factory & Extensions
# ----------------------------------------------------------------------

db = SQLAlchemy()
jwt = JWTManager()
bcrypt = Bcrypt()
limiter = Limiter(key_func=get_remote_address, storage_uri='memory://')

def create_app(config_name=None):
    """Application factory."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    app = Flask(__name__)
    app.config.from_object(config.get(config_name, DevelopmentConfig))

    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)

    # Security headers (Talisman)
    Talisman(
        app,
        force_https=app.config.get('TALISMAN_FORCE_HTTPS', False),
        strict_transport_security=app.config.get('TALISMAN_STRICT_TRANSPORT_SECURITY', True),
        session_cookie_secure=app.config.get('TALISMAN_SESSION_COOKIE_SECURE', True),
        content_security_policy={
            'default-src': "'self'",
            'script-src': "'self'",
            'style-src': "'self'"
        }
    )

    # Request logging & timing
    @app.before_request
    def start_timer():
        g.start_time = time.time()

    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            app.logger.info(
                '%s %s - %s (%.3fs)',
                request.method, request.path, response.status_code, duration
            )
        return response

    # Health check for container orchestration
    @app.route('/health')
    def health():
        return jsonify({"status": "healthy"})

    @app.route('/metrics')
    def metrics():
        return jsonify({
            "uptime": time.time() - app.config.get('START_TIME', time.time()),
            "status": "operational"
        })

    # Register blueprints (defined below)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(transactions_bp, url_prefix='/transactions')

    app.config['START_TIME'] = time.time()
    return app

# ----------------------------------------------------------------------
# 3. Database Models
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
        'Transaction', foreign_keys='Transaction.from_account_id', backref='source'
    )
    incoming_transactions = db.relationship(
        'Transaction', foreign_keys='Transaction.to_account_id', backref='destination'
    )

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
# 4. Request/Response Schemas (Marshmallow)
# ----------------------------------------------------------------------

class RegisterSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=3, max=80))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=6))  # Allow 6+ for tests


class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True)


class CreateAccountSchema(Schema):
    account_type = fields.Str(
        validate=validate.OneOf(['checking', 'savings']),
        load_default='checking'
    )
    currency = fields.Str(
        validate=validate.Regexp(r'^[A-Z]{3}$'),
        load_default='USD'
    )


class DepositSchema(Schema):
    account_id = fields.Int(required=True)
    amount = fields.Decimal(required=True, validate=validate.Range(min=Decimal('0.01'), max=Decimal('100000')))


class WithdrawSchema(Schema):
    account_id = fields.Int(required=True)
    amount = fields.Decimal(required=True, validate=validate.Range(min=Decimal('0.01'), max=Decimal('50000')))


class TransferSchema(Schema):
    from_account_id = fields.Int(required=True)
    to_account_id = fields.Int(required=True)
    amount = fields.Decimal(required=True, validate=validate.Range(min=Decimal('0.01'), max=Decimal('50000')))
    description = fields.Str(validate=validate.Length(max=200), load_default='')

# ----------------------------------------------------------------------
# 5. Helper Functions
# ----------------------------------------------------------------------

def generate_account_number():
    """Generate a unique account number."""
    import random
    import string
    while True:
        account_num = 'BANK-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not Account.query.filter_by(account_number=account_num).first():
            return account_num

def generate_transaction_reference():
    """Generate a unique transaction reference."""
    import random
    import string
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'TXN-{timestamp}-{random_part}'

def handle_validation_error(error):
    """Return validation errors as JSON."""
    return jsonify({
        'error': 'Validation Error',
        'message': error.messages,
        'status': 400
    }), 400

# ----------------------------------------------------------------------
# 6. JWT Callbacks
# ----------------------------------------------------------------------

@jwt.user_identity_loader
def user_identity_lookup(user):
    return user.id

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    # Use db.session.get() instead of Query.get() (legacy)
    return db.session.get(User, identity)

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    return False

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'error': 'Token Expired',
        'message': 'The access token has expired. Please refresh or re-authenticate.',
        'status': 401
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        'error': 'Invalid Token',
        'message': str(error),
        'status': 422
    }), 422

@jwt.unauthorized_loader
def unauthorized_callback(error):
    return jsonify({
        'error': 'Unauthorized',
        'message': 'Missing or invalid authorization token.',
        'status': 401
    }), 401

# ----------------------------------------------------------------------
# 7. Blueprints (defined inline)
# ----------------------------------------------------------------------

auth_bp = Blueprint('auth', __name__)
accounts_bp = Blueprint('accounts', __name__)
transactions_bp = Blueprint('transactions', __name__)

# ---------- Auth Blueprint ----------
@auth_bp.route('/register', methods=['POST'])
@limiter.limit('5 per hour')
def register():
    data = request.get_json()
    schema = RegisterSchema()
    try:
        validated = schema.load(data)
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

    access_token = create_access_token(identity=user)
    refresh_token = create_refresh_token(identity=user)
    return jsonify({
        'message': 'User created successfully',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict()
    }), 201

@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = request.get_json()
    schema = LoginSchema()
    try:
        validated = schema.load(data)
    except ValidationError as err:
        return handle_validation_error(err)

    user = User.query.filter_by(username=validated['username']).first()
    if not user or not user.check_password(validated['password']):
        return jsonify({'error': 'Invalid credentials', 'status': 401}), 401

    access_token = create_access_token(identity=user)
    refresh_token = create_refresh_token(identity=user)
    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict()
    }), 200

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    current_user = get_jwt_identity()
    access_token = create_access_token(identity=current_user)
    return jsonify({'access_token': access_token}), 200

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    return jsonify({'message': 'Successfully logged out'}), 200

# ---------- Accounts Blueprint ----------
@accounts_bp.route('', methods=['GET'])
@jwt_required()
def get_accounts():
    current_user_id = get_jwt_identity()
    accounts = Account.query.filter_by(user_id=current_user_id).all()
    return jsonify({'accounts': [acc.to_dict() for acc in accounts]}), 200

@accounts_bp.route('/<int:account_id>/balance', methods=['GET'])
@jwt_required()
def get_balance(account_id):
    current_user_id = get_jwt_identity()
    account = Account.query.filter_by(id=account_id, user_id=current_user_id).first()
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
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}
    schema = CreateAccountSchema()
    try:
        validated = schema.load(data)
    except ValidationError as err:
        return handle_validation_error(err)

    account = Account(
        account_number=generate_account_number(),
        account_type=validated['account_type'],
        currency=validated['currency'],
        user_id=current_user_id
    )
    db.session.add(account)
    db.session.commit()
    return jsonify({'message': 'Account created', 'account': account.to_dict()}), 201

# ---------- Transactions Blueprint ----------
@transactions_bp.route('/deposit', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def deposit():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    schema = DepositSchema()
    try:
        validated = schema.load(data)
    except ValidationError as err:
        return handle_validation_error(err)

    account = Account.query.filter_by(id=validated['account_id'], user_id=current_user_id).first()
    if not account:
        return jsonify({'error': 'Account not found', 'status': 404}), 404

    amount = validated['amount']  # Decimal
    account.balance += amount
    transaction = Transaction(
        amount=amount,
        type='deposit',
        status='completed',
        reference=generate_transaction_reference(),
        to_account_id=account.id
    )
    db.session.add(transaction)
    db.session.commit()

    return jsonify({
        'message': 'Deposit successful',
        'new_balance': str(account.balance),
        'transaction_id': transaction.id
    }), 200

@transactions_bp.route('/withdraw', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def withdraw():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    schema = WithdrawSchema()
    try:
        validated = schema.load(data)
    except ValidationError as err:
        return handle_validation_error(err)

    account = Account.query.filter_by(id=validated['account_id'], user_id=current_user_id).first()
    if not account:
        return jsonify({'error': 'Account not found', 'status': 404}), 404

    amount = validated['amount']  # Decimal
    if account.balance < amount:
        return jsonify({'error': 'Insufficient funds', 'status': 400}), 400

    account.balance -= amount
    transaction = Transaction(
        amount=amount,
        type='withdrawal',
        status='completed',
        reference=generate_transaction_reference(),
        from_account_id=account.id
    )
    db.session.add(transaction)
    db.session.commit()

    return jsonify({
        'message': 'Withdrawal successful',
        'new_balance': str(account.balance),
        'transaction_id': transaction.id
    }), 200

@transactions_bp.route('/transfer', methods=['POST'])
@jwt_required()
@limiter.limit('30 per minute')
def transfer():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    schema = TransferSchema()
    try:
        validated = schema.load(data)
    except ValidationError as err:
        return handle_validation_error(err)

    source_account = Account.query.filter_by(id=validated['from_account_id'], user_id=current_user_id).first()
    if not source_account:
        return jsonify({'error': 'Source account not found', 'status': 404}), 404

    dest_account = Account.query.filter_by(id=validated['to_account_id']).first()
    if not dest_account:
        return jsonify({'error': 'Destination account not found', 'status': 404}), 404

    amount = validated['amount']  # Decimal
    if source_account.balance < amount:
        return jsonify({'error': 'Insufficient funds', 'status': 400}), 400

    source_account.balance -= amount
    dest_account.balance += amount

    transaction = Transaction(
        amount=amount,
        type='transfer',
        status='completed',
        description=validated['description'],
        reference=generate_transaction_reference(),
        from_account_id=source_account.id,
        to_account_id=dest_account.id
    )
    db.session.add(transaction)
    db.session.commit()

    return jsonify({
        'message': 'Transfer successful',
        'source_balance': str(source_account.balance),
        'destination_account': dest_account.account_number,
        'transaction_id': transaction.id
    }), 200

@transactions_bp.route('/history', methods=['GET'])
@jwt_required()
def transaction_history():
    current_user_id = get_jwt_identity()
    user_accounts = Account.query.filter_by(user_id=current_user_id).all()
    account_ids = [acc.id for acc in user_accounts]

    transactions = Transaction.query.filter(
        db.or_(
            Transaction.from_account_id.in_(account_ids),
            Transaction.to_account_id.in_(account_ids)
        )
    ).order_by(Transaction.created_at.desc()).limit(100).all()

    return jsonify({
        'transactions': [txn.to_dict() for txn in transactions],
        'count': len(transactions)
    }), 200

# ----------------------------------------------------------------------
# 8. App Initialization
# ----------------------------------------------------------------------

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0' if os.environ.get('FLASK_ENV') == 'production' else '127.0.0.1')
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host=host, port=port, debug=debug)
