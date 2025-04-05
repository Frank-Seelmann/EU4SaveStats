from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from .forms import RegistrationForm, LoginForm
from app.auth_service import AuthService

auth_bp = Blueprint('auth', __name__, template_folder='templates')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            user = AuthService.register_user(
                form.username.data,
                form.email.data,
                form.password.data
            )
            if user:
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('auth.login'))
            flash('Username or email already exists', 'danger')
        except Exception as e:
            current_app.logger.error(f"Registration error: {str(e)}")
            flash('Registration failed. Please try again.', 'danger')
    
    return render_template('auth/register.html', form=form)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = AuthService.login_user(
                form.username.data,
                form.password.data
            )
            if user:
                login_user(user)
                flash('Logged in successfully!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('main.index'))
            flash('Invalid username or password', 'danger')
        except Exception as e:
            current_app.logger.error(f"Login error: {str(e)}")
            flash('Login failed. Please try again.', 'danger')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('main.index'))