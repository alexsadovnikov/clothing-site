import os
from io import BytesIO
from typing import Optional
from minio import Minio


def _client() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000").strip()
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")
    secure = os.getenv("MINIO_SECURE", "0").strip().lower() in ("1", "true", "yes")

    if not access_key or not secret_key:
        raise RuntimeError("MINIO_ACCESS_KEY/MINIO_SECRET_KEY are not set")

    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def ensure_bucket(bucket: Optional[str] = None) -> str:
    b = (bucket or os.getenv("MINIO_BUCKET") or os.getenv("MINIO_BUCKET_NAME") or "products").strip()
    if not b:
        raise ValueError("bucket is empty")

    c = _client()
    if not c.bucket_exists(b):
        c.make_bucket(b)
    return b


def put_object(
    *,
    data: bytes,
    content_type: str,
    object_key: Optional[str] = None,
    key: Optional[str] = None,
    bucket: Optional[str] = None,
) -> None:
    obj_key = (object_key or key or "").strip()
    if not obj_key:
        raise ValueError("object_key/key is required")

    b = ensure_bucket(bucket)

    c = _client()
    bio = BytesIO(data)
    c.put_object(b, obj_key, bio, length=len(data), content_type=content_type)
