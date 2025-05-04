import os
import boto3
from botocore.exceptions import ClientError
from .config import Config
from typing import Optional
import uuid

class S3Service:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(S3Service, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        if not Config.S3_ENABLED:
            self.client = None
            return
            
        try:
            session = boto3.session.Session()
            client_config = {
                'region_name': Config.S3_REGION,
                'aws_access_key_id': Config.S3_ACCESS_KEY,
                'aws_secret_access_key': Config.S3_SECRET_KEY
            }
            
            # Only add endpoint if specified
            if hasattr(Config, 'S3_ENDPOINT_URL') and Config.S3_ENDPOINT_URL:
                client_config['endpoint_url'] = Config.S3_ENDPOINT_URL
                
            self.client = session.client('s3', **client_config)
            
            # Test connection
            self.client.list_buckets()
        except Exception as e:
            print(f"Failed to initialize S3 client: {e}")
            self.client = None
    
    def upload_file(self, file_path: str, user_id: int) -> Optional[str]:
        """Upload a file to S3 and return its object key"""
        if not self.client:
            return None
            
        try:
            # Generate a unique object key
            file_name = os.path.basename(file_path)
            object_key = f"user_{user_id}/{uuid.uuid4().hex}_{file_name}"
            
            self.client.upload_file(
                Filename=file_path,
                Bucket=Config.S3_BUCKET,
                Key=object_key
            )
            return object_key
        except ClientError as e:
            print(f"Error uploading file to S3: {e}")
            return None
    
    def get_file_url(self, object_key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate a presigned URL for the file"""
        if not self.client or not object_key:
            return None
            
        try:
            return self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': Config.S3_BUCKET, 'Key': object_key},
                ExpiresIn=expires_in
            )
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            return None
    
    def delete_file(self, object_key: str) -> bool:
        """Delete a file from S3"""
        if not self.client or not object_key:
            return False
            
        try:
            self.client.delete_object(
                Bucket=Config.S3_BUCKET,
                Key=object_key
            )
            return True
        except ClientError as e:
            print(f"Error deleting file from S3: {e}")
            return False