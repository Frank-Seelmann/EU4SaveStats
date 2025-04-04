import subprocess
import json
from typing import Optional
from models import User

class AuthService:
    @staticmethod
    def register_user(username: str, email: str, password: str) -> Optional[User]:
        try:
            result = subprocess.run(
                ['./eu4_parser', 'register', username, email, password],
                capture_output=True,
                text=True,
                check=True
            )
            user_data = json.loads(result.stdout)
            return User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password_hash']
            )
        except subprocess.CalledProcessError as e:
            print(f"Registration failed: {e.stderr}")
            return None

    @staticmethod
    def login_user(username: str, password: str) -> Optional[User]:
        try:
            result = subprocess.run(
                ['./eu4_parser', 'login', username, password],
                capture_output=True,
                text=True,
                check=True
            )
            user_data = json.loads(result.stdout)
            return User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password_hash']
            )
        except subprocess.CalledProcessError as e:
            print(f"Login failed: {e.stderr}")
            return None
        

    @staticmethod
    def process_file(auth_token: str, s3_key: str) -> bool:
        try:
            result = subprocess.run(
                ['./eu4_parser', auth_token, s3_key],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"File processing failed: {e.stderr}")
            return False