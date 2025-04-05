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
            # Get current environment (preserve existing vars)
            env = os.environ.copy()
            
            env["DEBUG_MODE"] = "1"  # Force debug mode
            print("[DEBUG] AUTHENTICATION BYPASSED (DEBUG_MODE=1)")
            
            result = subprocess.run(
                ['./eu4_parser', auth_token, s3_key],  # Normal arguments
                capture_output=True,
                text=True,
                check=True,
                env=env  # Pass the modified environment
            )
            
            print("Rust Output:", result.stdout)
            if result.stderr:
                print("Rust Errors:", result.stderr)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Processing failed. Exit Code: {e.returncode}")
            print("Output:", e.stdout)
            print("Errors:", e.stderr)
            return False