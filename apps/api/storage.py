import os
from typing import Any, Dict

from fastapi import UploadFile
from minio import Minio


MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "products")
MINIO_SECURE = os.getenv("MINIO_SECURE", "0") == "1"
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", "").rstrip("/")


def _client() -> Minio:
    endpoint = MINIO_ENDPOINT.replace("http://", "").replace("https://", "").rstrip("/")
    return Minio(
        endpoint,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def upload_file_to_minio(*, file: UploadFile, object_key: str) -> Dict[str, Any]:
    """
    Единственная точка загрузки файлов в MinIO.

    Доменный термин: object_key (используется в API/БД/логике приложения).
    Технический термин SDK: object_name (используется только как параметр put_object).
    """
    if not object_key:
        raise ValueError("object_key is required")

    c = _client()

    if not c.bucket_exists(MINIO_BUCKET):
        c.make_bucket(MINIO_BUCKET)

    data = file.file
    data.seek(0, os.SEEK_END)
    size_bytes = data.tell()
    data.seek(0)

    c.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_key,  # SDK-параметр, значение — наш object_key
        data=data,
        length=size_bytes,
        content_type=file.content_type,
    )

    # URL для скачивания/просмотра снаружи (через публичный endpoint)
    url = ""
    if MINIO_PUBLIC_ENDPOINT:
        url = f"{MINIO_PUBLIC_ENDPOINT}/{MINIO_BUCKET}/{object_key}"

    return {
        "bucket": MINIO_BUCKET,
        "object_key": object_key,
        "size_bytes": size_bytes,
        "url": url,
    }