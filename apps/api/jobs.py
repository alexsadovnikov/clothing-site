from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

import requests
from meilisearch import Client as MeiliClient

from db import SessionLocal
from models import (
    AIJob,
    Media,
    Product,
    Category,
    ProductState,
    AIJobState,
)
from state_service import change_state

logger = logging.getLogger(__name__)

# =============================================================================
# MEILI CONFIG
# =============================================================================

_MEILI_FILTERABLE = ["status", "owner_id", "category_id", "tags"]
_MEILI_SORTABLE = ["updated_at"]


def _meili_cfg() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    host = (os.getenv("MEILI_HOST") or "").strip()
    key = (os.getenv("MEILI_MASTER_KEY") or "").strip()
    index_name = (os.getenv("MEILI_INDEX") or "products").strip()

    if not host or not key:
        return None, None, None

    if not host.startswith("http"):
        host = f"http://{host}"

    return host, key, index_name


def _task_uid(task_info) -> Optional[int]:
    if not task_info:
        return None
    if isinstance(task_info, dict):
        return task_info.get("taskUid") or task_info.get("uid")
    return getattr(task_info, "task_uid", None)


def _wait_task(client: MeiliClient, task_uid: int, timeout_s: int = 30) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            t = client.get_task(task_uid)
            if t.get("status") in ("succeeded", "failed"):
                return
        except Exception:
            pass
        time.sleep(0.25)


# =============================================================================
# MEILI INIT (SAFE FOR WORKER)
# =============================================================================

def init_meili() -> None:
    host, key, index_name = _meili_cfg()
    if not host or not key:
        logger.info("[meili] init skipped (not configured)")
        return

    client = MeiliClient(host, key)

    # ensure index exists
    try:
        idx = client.get_index(index_name)
    except Exception:
        task = client.create_index(index_name, {"primaryKey": "id_uuid"})
        if (uid := _task_uid(task)):
            _wait_task(client, uid)
        idx = client.get_index(index_name)

    # ensure settings
    settings = idx.get_settings()
    tasks: list[int] = []

    if sorted(settings.get("filterableAttributes", [])) != sorted(_MEILI_FILTERABLE):
        if (uid := _task_uid(idx.update_filterable_attributes(_MEILI_FILTERABLE))):
            tasks.append(uid)

    if sorted(settings.get("sortableAttributes", [])) != sorted(_MEILI_SORTABLE):
        if (uid := _task_uid(idx.update_sortable_attributes(_MEILI_SORTABLE))):
            tasks.append(uid)

    for uid in tasks:
        _wait_task(client, uid)

    logger.info("[meili] ready index=%s", index_name)


# =============================================================================
# HELPERS
# =============================================================================

def _update_product_text(product: Product, ai: dict) -> None:
    if not product.title and ai.get("title_suggested"):
        product.title = ai["title_suggested"]

    if not product.description:
        product.description = ai.get("description_draft") or "Описание будет уточнено."


# =============================================================================
# MAIN AI JOB
# =============================================================================

def process_ai_job(job_id: str) -> None:
    """
    Worker entrypoint.
    Полный цикл:
    AIJob → AI → Product(DRAFT) → link → DONE
    """
    t0 = time.perf_counter()

    # ------------------------------------------------------------------
    # 1️⃣ LOAD JOB + MEDIA
    # ------------------------------------------------------------------
    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not job:
            logger.warning("ai_job not found job_id=%s", job_id)
            return

        job.status = AIJobState.PROCESSING
        job.updated_at = datetime.utcnow()
        change_state(db, job, "ai_job", "start_processing", "system")

        media = db.query(Media).filter(Media.id == job.media_id).first()
        if not media:
            job.status = AIJobState.FAILED
            job.error = "media not found"
            db.commit()
            return

        db.commit()

    # ------------------------------------------------------------------
    # 2️⃣ CALL AI SERVICE
    # ------------------------------------------------------------------
    try:
        resp = requests.post(
            f"{os.getenv('AI_INTERNAL_URL', 'http://ai:8002')}/v1/analyze",
            json={"bucket": media.bucket, "object_key": media.object_key},
            timeout=(5, 120),
        )
        resp.raise_for_status()
        result = resp.json() or {}
    except Exception as e:
        with SessionLocal() as db:
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            if job:
                job.status = AIJobState.FAILED
                job.error = str(e)
                job.updated_at = datetime.utcnow()
                change_state(db, job, "ai_job", "ai_failed", "system")
                db.commit()
        logger.exception("AI request failed job_id=%s", job_id)
        return

    # ------------------------------------------------------------------
    # 3️⃣ CREATE PRODUCT (UUID PK)
    # ------------------------------------------------------------------
    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()

        product = Product(
            owner_id=job.owner_id,
            status=ProductState.DRAFT_EMPTY.value,
            title="Товар (черновик)",
            attributes={},
            tags=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(product)
        db.flush()  # ⬅️ id_uuid доступен

        _update_product_text(product, result)
        product.attributes = result.get("attributes") or {}
        product.tags = result.get("tags") or []

        job.status = AIJobState.DONE
        job.draft_product_id_uuid = product.id_uuid
        job.result = result
        job.updated_at = datetime.utcnow()

        change_state(db, job, "ai_job", "ai_done", "system")
        change_state(db, product, "product", "ready_for_publish", "system")

        db.commit()

    logger.info(
        "[ai] job done job_id=%s product_id_uuid=%s ms=%s",
        job_id,
        product.id_uuid,
        int((time.perf_counter() - t0) * 1000),
    )