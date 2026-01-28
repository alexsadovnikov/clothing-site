from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


def _bool(v: str | None) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _resolve_bucket_and_key(
    bucket: Optional[str],
    object_key: Optional[str],
    object_name: Optional[str],
) -> Tuple[str, str]:
    b = (bucket or os.getenv("MINIO_BUCKET") or "").strip()
    k = (object_key or object_name or "").strip()
    if not b:
        raise RuntimeError("MINIO_BUCKET is required (bucket param or env)")
    if not k:
        raise RuntimeError("object_key/object_name is required")
    return b, k


def _parse_public_endpoint(public: str) -> Tuple[str, bool]:
    """
    Accepts:
      - "http://127.0.0.1:9100"
      - "https://minio.example.com"
      - "127.0.0.1:9100"
    Returns:
      (endpoint_without_scheme, secure_bool)
    """
    p = public.strip()
    if "://" not in p:
        p = "http://" + p

    u = urlparse(p)
    if not u.hostname:
        raise RuntimeError(f"Invalid MINIO_PUBLIC_ENDPOINT: {public}")

    secure = (u.scheme == "https")
    endpoint = u.netloc  # host:port
    return endpoint, secure


def get_minio_internal_client() -> Minio:
    """
    Internal client for container-to-container traffic.
    Must use MINIO_ENDPOINT like "minio:9000" (NO scheme).
    """
    endpoint = (os.getenv("MINIO_ENDPOINT") or "").strip()
    access = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
    secret = (os.getenv("MINIO_SECRET_KEY") or "").strip()
    secure = _bool(os.getenv("MINIO_SECURE"))
    region = (os.getenv("MINIO_REGION") or "us-east-1").strip()

    if not endpoint:
        raise RuntimeError("MINIO_ENDPOINT is required")
    if "://" in endpoint:
        raise RuntimeError("MINIO_ENDPOINT must NOT include scheme (use 'minio:9000', not 'http://...')")

    if not access or not secret:
        raise RuntimeError("MINIO_ACCESS_KEY / MINIO_SECRET_KEY are required")

    return Minio(
        endpoint=endpoint,
        access_key=access,
        secret_key=secret,
        secure=secure,
        region=region,
    )


def get_minio_presign_client(bucket_for_region: Optional[str] = None) -> Minio:
    """
    Client used ONLY for presigned URL generation.

    IMPORTANT:
      - The URL must be signed for PUBLIC host (MINIO_PUBLIC_ENDPOINT) because host is in SigV4.
      - But container MUST NOT try to connect to PUBLIC host (127.0.0.1:9100) to resolve bucket region.
      - Therefore: resolve region via INTERNAL client, then inject into presign client's region cache.
    """
    access = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
    secret = (os.getenv("MINIO_SECRET_KEY") or "").strip()
    region_default = (os.getenv("MINIO_REGION") or "us-east-1").strip()

    if not access or not secret:
        raise RuntimeError("MINIO_ACCESS_KEY / MINIO_SECRET_KEY are required")

    public = (os.getenv("MINIO_PUBLIC_ENDPOINT") or "").strip()
    if public:
        endpoint, secure = _parse_public_endpoint(public)

        presign_client = Minio(
            endpoint=endpoint,
            access_key=access,
            secret_key=secret,
            secure=secure,
            region=region_default,
        )

        # Resolve bucket region via internal connectivity and cache it in presign client
        if bucket_for_region:
            try:
                internal = get_minio_internal_client()
                bucket_region = internal._get_region(bucket_for_region)  # uses minio:9000
                # MinIO python keeps regions in an internal map; prefill to avoid call to PUBLIC host
                if not hasattr(presign_client, "_region_map") or presign_client._region_map is None:
                    presign_client._region_map = {}
                presign_client._region_map[bucket_for_region] = bucket_region
            except Exception:
                # If anything goes wrong, at least do not crash here; fall back to default region.
                logger.exception("[minio] failed to prefill region cache for presign bucket=%s", bucket_for_region)

        return presign_client

    # fallback: sign for internal endpoint (works only if client can reach it)
    return get_minio_internal_client()


def ensure_bucket(bucket: Optional[str] = None) -> None:
    bucket = (bucket or os.getenv("MINIO_BUCKET") or "").strip()
    if not bucket:
        raise RuntimeError("MINIO_BUCKET is required")

    client = get_minio_internal_client()
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("[minio] bucket created name=%s", bucket)
        else:
            logger.info("[minio] bucket ok name=%s", bucket)
    except S3Error:
        logger.exception("[minio] ensure_bucket failed bucket=%s", bucket)
        raise


def upload_file_to_minio(
    *,
    file,
    object_key: Optional[str] = None,
    object_name: Optional[str] = None,
    bucket: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified uploader: prefers object_key, but supports object_name for backward compatibility.
    Returns bucket, object_key, size_bytes, etag, content_type.
    """
    bucket, key = _resolve_bucket_and_key(bucket, object_key, object_name)
    client = get_minio_internal_client()

    f = file.file  # Starlette UploadFile underlying file
    size_bytes: int | None = None
    try:
        f.seek(0, 2)
        size_bytes = int(f.tell())
        f.seek(0)
    except Exception:
        try:
            f.seek(0)
        except Exception:
            pass
        size_bytes = None

    content_type = getattr(file, "content_type", None)

    if size_bytes is not None:
        client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=f,
            length=size_bytes,
            content_type=content_type,
        )
    else:
        client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=f,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=content_type,
        )

    st = client.stat_object(bucket, key)
    return {
        "bucket": bucket,
        "object_key": key,
        "size_bytes": int(st.size),
        "etag": st.etag,
        "content_type": content_type,
    }


def presign_get_object(
    *,
    object_key: Optional[str] = None,
    object_name: Optional[str] = None,
    bucket: Optional[str] = None,
    expires_seconds: int = 3600,
) -> str:
    """
    Generate presigned URL that is VALID for the public endpoint.
    No host rewriting after signing (it breaks signature).
    Also does not attempt to contact MINIO_PUBLIC_ENDPOINT from inside container.
    """
    bucket, key = _resolve_bucket_and_key(bucket, object_key, object_name)

    client = get_minio_presign_client(bucket_for_region=bucket)

    return client.presigned_get_object(
        bucket_name=bucket,
        object_name=key,
        expires=timedelta(seconds=int(expires_seconds)),
    )


def get_object_stream(
    *,
    object_key: Optional[str] = None,
    object_name: Optional[str] = None,
    bucket: Optional[str] = None,
):
    """
    Returns MinIO response object (urllib3) for streaming.
    Caller must close it.
    """
    bucket, key = _resolve_bucket_and_key(bucket, object_key, object_name)
    client = get_minio_internal_client()
    return client.get_object(bucket_name=bucket, object_name=key)


def healthcheck() -> None:
    ensure_bucket()