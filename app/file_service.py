import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from .database import Database
from datetime import datetime
import subprocess
from .s3_service import S3Service

class FileService:
    PROCESSED_DIR = "processed"
    
    @staticmethod
    def ensure_processed_dir() -> str:
        """Ensure processed directory exists and return its path"""
        os.makedirs(FileService.PROCESSED_DIR, exist_ok=True)
        return FileService.PROCESSED_DIR

    @staticmethod
    def calculate_checksum(file_path: str) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    def process_file(file_path: str, user_id: int) -> Dict[str, Any]:
        """Process a file and save all data to database atomically"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Initialize S3 service
        s3 = S3Service()
        s3_key = None

        # Get paths
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rust_binary = os.path.join(project_root, "eu4_parser.exe")
        input_file = os.path.join(project_root, file_path)
        processed_dir = os.path.join(project_root, "processed")
        os.makedirs(processed_dir, exist_ok=True)

        json_path = None
        db = Database()
        conn = db._get_connection()  # Get a single connection for the entire process
        
        try:
            # 1. Upload original file to S3
            s3_key = s3.upload_file(file_path, user_id)

            # 2. Process file with Rust binary
            try:
                result = subprocess.run(
                    [rust_binary, input_file, str(user_id)],
                    cwd=project_root,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                # Extract and clean up the error message
                error_msg = (e.stderr.strip() if e.stderr else "No error message from parser")
                
                # Create a clean error message
                clean_error = (
                    "⚠️ File Processing Failed ⚠️\n"
                    f"Error: {error_msg}\n\n"
                    "Possible solutions:\n"
                    "- Ensure the file is uncompressed\n"
                    "- Use a non-Ironman save file\n"
                    "- Verify the file is a valid EU4 save\n\n"
                    "Technical details available in server logs"
                )
                
                user_error = RuntimeError(clean_error)
                # Attach the full error as an attribute
                user_error.full_error = str(e)
                raise user_error from None

            # 3. Find the generated JSON file
            json_files = [
                f for f in os.listdir(processed_dir)
                if f.endswith('.json') and f.startswith(Path(file_path).stem)
            ]
            if not json_files:
                raise RuntimeError("No output JSON file was generated. The parser may have failed silently.")

            json_files.sort(key=lambda f: os.path.getmtime(os.path.join(processed_dir, f)))
            json_file = json_files[-1]
            json_path = os.path.join(processed_dir, json_file)

            # 4. Load the processed data
            with open(json_path, 'r', encoding='utf-8') as f:
                output = json.load(f)
            checksum = output['file_checksum']

            # 5. Save all country data in a transaction
            for country_data in output.get('processed_data', []):
                db.save_all_country_data(conn, checksum, country_data)

            # 6. Register file processing with S3 key
            db.register_file_processing(
                conn,
                original_filename=os.path.basename(file_path),
                checksum=checksum,
                json_path=json_path,
                user_id=user_id,
                s3_key=s3_key
            )

            # Commit the entire transaction
            conn.commit()

            return {
                'original_file': file_path,
                'json_output': json_path,
                'checksum': checksum,
                'user_id': user_id,
                'data': output,
                's3_key': s3_key
            }

        except Exception as e:
            # Rollback on any error
            if conn:
                conn.rollback()
            # Clean up S3 file if it was uploaded
            if s3_key:
                s3.delete_file(s3_key)
            # Clean up JSON file if it was created
            if json_path and os.path.exists(json_path):
                os.remove(json_path)
            raise RuntimeError(f"Processing failed: {str(e)}") from e

        finally:
            if conn:
                conn.close()

    @staticmethod
    def get_user_files(user_id: int) -> List[Dict[str, Any]]:
        """Get list of processed files for a user"""
        db = Database()
        files = db.get_user_files(user_id)
        
        # Add additional file metadata from the processed JSON
        result = []
        for file in files:
            try:
                with open(file['json_path'], 'r') as f:
                    file_data = json.load(f)
                    file.update({
                        'original_filename': file_data.get('original_filename'),
                        'processed_at': file_data.get('timestamp'),
                        'countries': [c['country_tag'] for c in file_data.get('processed_data', [])]
                    })
                    result.append(file)
            except Exception as e:
                print(f"Error loading file {file['id']}: {e}")
        
        return result