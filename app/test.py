from app.s3_service import S3Service

s3 = S3Service()
if s3.client is None:
    print("S3 client not initialized. Check your .env configuration.")
else:
    print("S3 client initialized successfully")
    result = s3.upload_file("app/test.py", 1)
    if result:
        print(f"File uploaded successfully. Key: {result}")
    else:
        print("File upload failed")