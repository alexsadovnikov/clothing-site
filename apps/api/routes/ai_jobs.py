# apps/api/routes/ai_jobs.py
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Optional, Dict, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.db import get_db
from apps.api.models import AIJob, Media, User

# два режима: queue (через enqueue) или direct (в фоне прямо из API)
from apps.api.queueing import enqueue_process_job
from apps.api.jobs import process_ai_job

router = APIRouter(prefix="/v1/ai", tags=["ai"])

RunMode = Literal["queue", "direct"]


class AIJobCreateIn(BaseModel):
    media_id: str = Field(..., description="Media UUID")
    hint: Optional[Dict[str, Any]] = None


def _get_run_mode() -> RunMode:
    """
    Продовый дефолт — queue.
    direct оставляем только для dev/e2e.
    """
    mode = (os.getenv("AI_RUN_MODE") or "queue").strip().lower()
    return "direct" if mode == "direct" else "queue"


def _draft_id_from_job(job: AIJob) -> str | None:
    """
    В БД и модели фактически используется draft_product_id.
    Ранее тут ошибочно читалось draft_product_id_uuid, из-за чего фронт не получал id черновика.
    """
    v = getattr(job, "draft_product_id", None)
    return str(v) if v else None


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_ai_job(
    payload: AIJobCreateIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # 1) проверяем, что media существует и принадлежит пользователю
    media = db.query(Media).filter(Media.id == payload.media_id).first()
    if not media or str(media.owner_id) != str(current.id):
        raise HTTPException(status_code=404, detail="media not found")

    # 2) создаём AIJob
    job_id = str(uuid.uuid4())
    now = datetime.utcnow()

    job = AIJob(
        id=job_id,
        owner_id=current.id,
        media_id=media.id,
        status="queued",
        hint=payload.hint or {},
        created_at=now,
        updated_at=now,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # 3) запускаем обработку
    mode: RunMode = _get_run_mode()

    if mode == "queue":
        try:
            enqueue_process_job(job_id)
        except Exception as e:
            # Важно: не оставляем job в вечном queued
            try:
                job.status = "failed"
                setattr(job, "error", f"enqueue_failed: {e.__class__.__name__}: {e}")
                job.updated_at = datetime.utcnow()
                db.add(job)
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(
                status_code=503,
                detail="failed to enqueue ai job",
            ) from e
    else:
        # direct — только dev/e2e: без очереди, но в фоне
        background.add_task(process_ai_job, job_id)

    return {
        "job_id": job_id,
        "status": "queued",
        "run_mode": mode,
        "enqueued": True,
    }


@router.get("/jobs/{job_id}")
def get_ai_job(
    job_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    job = db.query(AIJob).filter(AIJob.id == job_id).first()
    if not job or str(job.owner_id) != str(current.id):
        raise HTTPException(status_code=404, detail="job not found")

    # В БД это result_json, а не result — поэтому раньше всегда было null
    result = getattr(job, "result_json", None)

    return {
        "job_id": str(job.id),
        "status": str(job.status),
        "error": getattr(job, "error", None),
        "draft_product_id": _draft_id_from_job(job),
        "result": result,
        "updated_at": job.updated_at.isoformat() if getattr(job, "updated_at", None) else None,
        "created_at": job.created_at.isoformat() if getattr(job, "created_at", None) else None,
    }