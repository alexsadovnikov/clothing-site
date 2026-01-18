from __future__ import annotations

import os
import io
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from minio import Minio

from db import SessionLocal
from models import Media
from auth import get_current_user


router = APIRouter(prefix="/v1/media", tags=["media"])


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_minio() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT")
    if not endpoint:
        raise RuntimeError("MINIO_ENDPOINT is not set")

    endpoint = endpoint.replace("http://", "").replace("https://", "")

    return Minio(
        endpoint,
        access_key=os.getenv("MINIO_ACCESS_KEY"),
        secret_key=os.getenv("MINIO_SECRET_KEY"),
        secure=os.getenv("MINIO_SECURE", "0") == "1",
    )


# -----------------------------------------------------------------------------
# UPLOAD
# -----------------------------------------------------------------------------

@router.post("/upload")
def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    bucket = os.getenv("MINIO_BUCKET", "products")
    minio = get_minio()

    if not minio.bucket_exists(bucket):
        minio.make_bucket(bucket)

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    size_bytes = len(content)
    ext = os.path.splitext(file.filename or "")[1]
    object_key = f"{current_user.id}/{uuid.uuid4()}{ext}"

    minio.put_object(
        bucket_name=bucket,
        object_name=object_key,
        data=io.BytesIO(content),
        length=size_bytes,
        content_type=file.content_type or "application/octet-stream",
    )

    media = Media(
        id=str(uuid.uuid4()),
        owner_id=current_user.id,
        bucket=bucket,
        object_key=object_key,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        checksum_sha256=None,
        created_at=datetime.utcnow(),
    )

    db.add(media)
    db.commit()
    db.refresh(media)

    return {
        "media_id": media.id,
        "bucket": media.bucket,
        "object_key": media.object_key,
        "size_bytes": media.size_bytes,
    }


# -----------------------------------------------------------------------------
# GET media info
# -----------------------------------------------------------------------------

@router.get("/{media_id}")
def get_media(
    media_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(status_code=404, detail="media not found")

    if media.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="access denied")

    return {
        "id": media.id,
        "bucket": media.bucket,
        "object_key": media.object_key,
        "content_type": media.content_type,
        "size_bytes": media.size_bytes,
        "created_at": media.created_at,
    }


# -----------------------------------------------------------------------------
# HEAD media (metadata only)
# -----------------------------------------------------------------------------

@router.head("/{media_id}")
def head_media(
    media_id: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(status_code=404, detail="media not found")

    if media.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="access denied")

    response.headers["Content-Type"] = media.content_type
    response.headers["Content-Length"] = str(media.size_bytes)
    response.headers["X-Media-Id"] = media.id

    return Response(status_code=200)


# -----------------------------------------------------------------------------
# PRESIGNED DOWNLOAD (CORRECT)
# -----------------------------------------------------------------------------

@router.get("/{media_id}/download")
def download_media(
    media_id: str,
    expires_in: int = 600,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(status_code=404, detail="media not found")

    if media.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="access denied")

    minio = get_minio()

    try:
        raw_url = minio.presigned_get_object(
            media.bucket,
            media.object_key,
            expires=timedelta(seconds=expires_in),
        )
    except Exception:
        raise HTTPException(status_code=500, detail="cannot generate download url")

    public_minio = os.getenv("MINIO_PUBLIC_ENDPOINT")
    if not public_minio:
        raise HTTPException(status_code=500, detail="MINIO_PUBLIC_ENDPOINT not set")

    internal = os.getenv("MINIO_ENDPOINT") \
        .replace("http://", "") \
        .replace("https://", "")

    external = public_minio \
        .replace("http://", "") \
        .replace("https://", "")

    download_url = raw_url.replace(internal, external)

    return {
        "media_id": media.id,
        "download_url": download_url,
        "expires_in": expires_in,
    }


# -----------------------------------------------------------------------------
# DELETE media
# -----------------------------------------------------------------------------

@router.delete("/{media_id}")
def delete_media(
    media_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(status_code=404, detail="media not found")

    if media.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="access denied")

    try:
        minio = get_minio()
        minio.remove_object(media.bucket, media.object_key)
    except Exception:
        pass  # best-effort

    db.delete(media)
    db.commit()

    return {
        "status": "deleted",
        "media_id": media_id,
    }