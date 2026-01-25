from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.db import get_db
from apps.api.models import Media, User
from apps.api.storage import upload_file_to_minio, presign_get_object

router = APIRouter(prefix="/v1/media", tags=["media"])


@router.post("/upload")
def upload_media(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    if not file or not getattr(file, "filename", None):
        raise HTTPException(status_code=400, detail="file is required")

    media_id = str(uuid.uuid4())
    bucket = "products"
    object_key = f"{current.id}/{media_id}_{file.filename}"

    result = upload_file_to_minio(file=file, object_key=object_key, bucket=bucket)

    # Persist Media row
    m = Media(
        id=media_id,
        owner_id=current.id,
        bucket=bucket,
        object_key=object_key,
        filename=file.filename or "",
        content_type=result.get("content_type"),
        size_bytes=(result.get("size_bytes") or 0),
    )
    db.add(m)
    db.commit()

    # IMPORTANT: return browser-friendly URL via API endpoint (dev/prod parity)
    return {
        "id": m.id,
        "bucket": m.bucket,
        "object_key": m.object_key,
        "filename": m.filename,
        "content_type": m.content_type,
        "size_bytes": m.size_bytes,
        "content_url": f"/api/v1/media/{m.id}/content",
    }


@router.get("/{media_id}/content")
def get_media_content(
    media_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    m = db.query(Media).filter(Media.id == media_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="media not found")

    # ACL: only owner can access
    if m.owner_id != current.id:
        raise HTTPException(status_code=403, detail="forbidden")

    url = presign_get_object(bucket=m.bucket, object_key=m.object_key, expires_seconds=900)
    return RedirectResponse(url=url, status_code=302)
