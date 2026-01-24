import uuid
import logging
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.auth import get_current_user
from apps.api.models import User, Media
from apps.api.storage import upload_file_to_minio

router = APIRouter(prefix="/v1/media", tags=["media"])
logger = logging.getLogger("media.upload")


@router.post("/upload", operation_id="upload_media")
def upload_media(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    request_id = request.headers.get("X-Request-ID", "unknown")

    logger.info(
        "MEDIA_UPLOAD_START request_id=%s user_id=%s filename=%s",
        request_id,
        current.id,
        getattr(file, "filename", None),
    )

    try:
        if not file or not file.filename:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "bad_request",
                    "detail": "file is required",
                    "request_id": request_id,
                },
            )

        media_id = str(uuid.uuid4())
        object_key = f"{current.id}/{media_id}_{file.filename}"

        logger.debug(
            "MINIO_UPLOAD request_id=%s object_key=%s content_type=%s",
            request_id,
            object_key,
            file.content_type,
        )

        result = upload_file_to_minio(file=file, object_key=object_key)

        logger.debug("MINIO_RESULT request_id=%s result=%s", request_id, result)

        media = Media(
            id=media_id,
            owner_id=current.id,
            filename=file.filename,              # ✅ ВОТ ЭТОГО НЕ ХВАТАЛО
            bucket=result["bucket"],
            object_key=result["object_key"],
            content_type=file.content_type,
            size_bytes=result["size_bytes"],
            created_at=datetime.utcnow(),
        )

        db.add(media)
        db.commit()
        db.refresh(media)

        logger.info(
            "MEDIA_UPLOAD_OK request_id=%s media_id=%s",
            request_id,
            media.id,
        )

        return {
            "id": media.id,
            "bucket": media.bucket,
            "object_key": media.object_key,
            "filename": media.filename,          # ✅ можно вернуть тоже
            "content_type": media.content_type,
            "size_bytes": media.size_bytes,
            "url": result["url"],
        }

    except Exception as e:
        logger.error("MEDIA_UPLOAD_FAILED request_id=%s error=%s", request_id, str(e))
        logger.error("TRACEBACK request_id=%s\n%s", request_id, traceback.format_exc())

        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": str(e),
                "request_id": request_id,
            },
        )