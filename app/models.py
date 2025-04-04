from flask_login import UserMixin
import subprocess

class User(UserMixin):
    def __init__(self, id, username, email, password_hash):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash

    def verify_password(self, password: str) -> bool:
        """Verify password using Rust backend"""
        try:
            result = subprocess.run(
                ['./eu4_parser', 'verify', str(self.id), password],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip() == "true"
        except subprocess.CalledProcessError:
            return False