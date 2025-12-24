import os
from minio import Minio

def _client() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")
    secure = os.getenv("MINIO_SECURE", "0") == "1"
    if not access_key or not secret_key:
        raise RuntimeError("MINIO_ACCESS_KEY/MINIO_SECRET_KEY are not set")
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

def ensure_bucket():
    bucket = os.getenv("MINIO_BUCKET", "products")
    c = _client()
    if not c.bucket_exists(bucket):
        c.make_bucket(bucket)

def put_object(object_key: str, data: bytes, content_type: str):
    bucket = os.getenv("MINIO_BUCKET", "products")
    c = _client()
    from io import BytesIO
    bio = BytesIO(data)
    c.put_object(bucket, object_key, bio, length=len(data), content_type=content_type)