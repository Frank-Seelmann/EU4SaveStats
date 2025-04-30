from flask import Flask
from flask_login import LoginManager
from .config import Config
from .models import User
from .database import Database
from .auth_service import AuthService
import os

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    login_manager.init_app(app)
    
    # Initialize database
    Database()  # This will create tables if they don't exist

    # Create necessary directories
    os.makedirs(os.path.join(app.instance_path, 'temp'), exist_ok=True)
    os.makedirs('processed', exist_ok=True)

    # Register blueprints - IMPORTANT: Do this after other initializations
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .friends.routes import friends_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(friends_bp)

    return app

@login_manager.user_loader
def load_user(user_id):
    db = Database()
    conn = db._get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        user_data = cursor.fetchone()
        if user_data:
            return User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password_hash']
            )
        return None
    finally:
        cursor.close()
        conn.close()