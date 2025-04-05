import bcrypt
from .database import Database
from .models import User
from typing import Optional

class AuthService:
    @staticmethod
    def register_user(username: str, email: str, password: str) -> Optional[User]:
        """Register a new user with password hashing"""
        db = Database()
        conn = db._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Check if user exists
            cursor.execute('SELECT id FROM users WHERE username = %s OR email = %s', 
                         (username, email))
            if cursor.fetchone():
                return None
            
            # Hash password
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Create user
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            
            return User(user_id, username, email, password_hash)
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def login_user(username: str, password: str) -> Optional[User]:
        """Authenticate user and return User object if successful"""
        db = Database()
        conn = db._get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
            user_data = cursor.fetchone()
            
            if user_data and bcrypt.checkpw(password.encode('utf-8'), 
                                          user_data['password_hash'].encode('utf-8')):
                return User(
                    user_data['id'],
                    user_data['username'],
                    user_data['email'],
                    user_data['password_hash']
                )
            return None
        finally:
            cursor.close()
            conn.close()