from flask import Flask
from flask_login import LoginManager
from app.config import Config
from app.models import User
from app.utils import get_db_connection
import os

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(user_data['id'], user_data['username'], user_data['email'], user_data['password_hash'])
    return None

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    login_manager.init_app(app)

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.friends.routes import friends_bp
    from app.main.routes import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(main_bp)

    os.makedirs(os.path.join(app.instance_path, 'temp'), exist_ok=True)

    return app