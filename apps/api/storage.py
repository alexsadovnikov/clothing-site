from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import UploadFile
from minio import Minio


def _minio_client(endpoint: str, secure: bool) -> Minio:
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def get_internal_minio() -> Minio:
    """
    Internal endpoint reachable from containers (default: minio:9000).
    Use this for uploads and server-to-server operations.
    """
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    return _minio_client(endpoint, secure)


def get_public_minio_for_presign() -> Minio:
    """
    Public endpoint used for presigned URLs (must be reachable by browser).
    If MINIO_PUBLIC_ENDPOINT is not set, fall back to MINIO_ENDPOINT, which may break browser access.
    """
    endpoint = os.getenv("MINIO_PUBLIC_ENDPOINT") or os.getenv("MINIO_ENDPOINT", "minio:9000")
    secure = os.getenv("MINIO_PUBLIC_SECURE", os.getenv("MINIO_SECURE", "false")).lower() == "true"
    return _minio_client(endpoint, secure)


def upload_file_to_minio(*, file: UploadFile, object_key: str, bucket: str = "products") -> Dict[str, Any]:
    """
    Uploads file to MinIO bucket.
    Returns metadata about stored object.
    """
    c = get_internal_minio()

    # Ensure bucket exists (idempotent)
    if not c.bucket_exists(bucket):
        c.make_bucket(bucket)

    # Determine size (UploadFile may or may not support seek/tell reliably)
    size_bytes: int = 0
    try:
        pos = file.file.tell()
        file.file.seek(0, 2)
        size_bytes = int(file.file.tell())
        file.file.seek(pos)
    except Exception:
        # best-effort; DB may store 0 if unknown
        size_bytes = 0

    content_type = getattr(file, "content_type", None) or "application/octet-stream"

    # Important: MinIO python SDK uses "object_name" parameter
    c.put_object(
        bucket_name=bucket,
        object_name=object_key,
        data=file.file,
        length=size_bytes if size_bytes > 0 else -1,
        content_type=content_type,
        part_size=10 * 1024 * 1024,
    )

    return {
        "bucket": bucket,
        "object_key": object_key,
        "content_type": content_type,
        "size_bytes": size_bytes if size_bytes > 0 else None,
    }


def presign_get_object(*, bucket: str, object_key: str, expires_seconds: int = 900) -> str:
    """
    Generates browser-usable presigned GET URL.
    NOTE: requires MINIO_PUBLIC_ENDPOINT to be publicly reachable for real browser access.
    """
    c = get_public_minio_for_presign()
    return c.presigned_get_object(
        bucket_name=bucket,
        object_name=object_key,
        expires=timedelta(seconds=int(expires_seconds)),
    )

# Backward-compatible alias required by apps/api/main.py
def ensure_bucket(bucket: str) -> None:
    for name in ("ensure_minio_bucket", "ensure_bucket_exists", "create_bucket_if_not_exists"):
        fn = globals().get(name)
        if callable(fn):
            return fn(bucket)

    get_client = globals().get("get_minio_client") or globals().get("get_client")
    if callable(get_client):
        client = get_client()
        if hasattr(client, "bucket_exists") and hasattr(client, "make_bucket"):
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            return

    raise ImportError("ensure_bucket alias cannot find underlying MinIO helper in apps.api.storage")
