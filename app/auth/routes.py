from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user
from app.models import User
from app.utils import get_db_connection
from .forms import RegistrationForm, LoginForm
import subprocess

auth_bp = Blueprint('auth', __name__, template_folder='templates')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        
        try:
            # Use Rust backend for registration to ensure consistent hashing
            result = subprocess.run(
                ['./eu4_parser', 'register', username, email, password],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                flash(f'Registration failed: {result.stderr}', 'danger')
            else:
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('auth.login'))
                
        except Exception as e:
            flash(f'Error during registration: {str(e)}', 'danger')
    
    return render_template('auth/register.html', form=form)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        try:
            # First try authenticating with Rust backend
            result = subprocess.run(
                ['./eu4_parser', 'login', username, password],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # If Rust auth succeeds, get user from database
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
                user_data = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if user_data:
                    user = User(
                        user_data['id'], 
                        user_data['username'], 
                        user_data['email'], 
                        user_data['password_hash']
                    )
                    login_user(user)
                    flash('Logged in successfully!', 'success')
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('main.index'))
            
            # If we get here, authentication failed
            flash('Invalid username or password', 'danger')
            
        except Exception as e:
            current_app.logger.error(f"Login error: {str(e)}")
            flash('Login error occurred', 'danger')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('main.index'))