from app.app import create_app, db

app = create_app('development')   # or 'production'
with app.app_context():
    db.create_all()
    print("Database tables created.")
