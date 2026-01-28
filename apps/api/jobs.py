from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import Optional, Tuple

import requests
from meilisearch import Client as MeiliClient

from apps.api.db import SessionLocal
from apps.api.models import AIJob, Media, Product, ProductState, AIJobState
from apps.api.state_service import change_state

logger = logging.getLogger(__name__)

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


def init_meili() -> None:
    host, key, index_name = _meili_cfg()
    if not host or not key:
        logger.info("[meili] init skipped (not configured)")
        return

    client = MeiliClient(host, key)

    try:
        idx = client.get_index(index_name)
    except Exception:
        task = client.create_index(index_name, {"primaryKey": "id"})
        if (uid := _task_uid(task)):
            _wait_task(client, uid)
        idx = client.get_index(index_name)

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


def _update_product_text(product: Product, ai: dict) -> None:
    if not product.title and ai.get("title_suggested"):
        product.title = ai["title_suggested"]

    if not product.description:
        product.description = ai.get("description_draft") or "Описание будет уточнено."


def _set_ai_job_state(*, job: AIJob, status: str, error: str | None = None) -> None:
    job.status = status
    job.updated_at = datetime.utcnow()

    if status in (AIJobState.RUNNING.value, AIJobState.SUCCEEDED.value):
        job.error = None

    if error is not None:
        job.error = error


def _ai_internal_base_url() -> str:
    # worker calls api service in docker network
    return (os.getenv("AI_INTERNAL_URL") or "http://api:8001").strip().rstrip("/")


def _ai_internal_token() -> str:
    # shared internal token (worker->api and api->gateway)
    return (os.getenv("AI_INTERNAL_TOKEN") or "").strip()


def _safe_json(resp: requests.Response) -> dict:
    try:
        data = resp.json() or {}
    except Exception as e:
        raise ValueError(f"AI response is not JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object")

    return data


def process_ai_job(job_id: str) -> None:
    """
    Worker entrypoint.
    AIJob -> call internal /v1/analyze -> create Product(DRAFT) -> transition -> SUCCEEDED/FAILED
    """
    t0 = time.perf_counter()

    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not job:
            logger.warning("ai_job not found job_id=%s", job_id)
            return

        if job.status == AIJobState.SUCCEEDED.value and job.draft_product_id:
            if job.error:
                _set_ai_job_state(job=job, status=AIJobState.SUCCEEDED.value, error=None)
                db.commit()

            logger.info(
                "[ai] job already succeeded job_id=%s draft_product_id=%s",
                job_id,
                job.draft_product_id,
            )
            return

        _set_ai_job_state(job=job, status=AIJobState.RUNNING.value)

        media = db.query(Media).filter(Media.id == job.media_id).first()
        if not media:
            _set_ai_job_state(job=job, status=AIJobState.FAILED.value, error="media not found")
            db.commit()
            return

        media_bucket = media.bucket
        media_object_key = media.object_key
        db.commit()

    base = _ai_internal_base_url()
    url = f"{base}/v1/analyze"

    token = _ai_internal_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-AI-Internal-Token"] = token  # <-- КЛЮЧЕВОЙ ФИКС

    try:
        resp = requests.post(
            url,
            json={"bucket": media_bucket, "object_key": media_object_key},
            headers=headers,
            timeout=(5, 180),
        )
        resp.raise_for_status()
        result = _safe_json(resp)

    except Exception as e:
        with SessionLocal() as db:
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            if job:
                _set_ai_job_state(job=job, status=AIJobState.FAILED.value, error=str(e))
                db.commit()

        logger.exception("AI request failed job_id=%s url=%s", job_id, url)
        raise

    product_id: str | None = None

    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not job:
            logger.warning("ai_job disappeared job_id=%s", job_id)
            return

        product = Product(
            owner_id=job.owner_id,
            status=ProductState.DRAFT_EMPTY.value,
            title="Товар (черновик)",
            attributes={},
            tags=[],
        )
        db.add(product)
        db.flush()

        product_id = product.id

        _update_product_text(product, result)
        product.attributes = result.get("attributes") or {}
        product.tags = result.get("tags") or []

        _set_ai_job_state(job=job, status=AIJobState.SUCCEEDED.value)
        job.draft_product_id = product.id
        job.result_json = result

        try:
            change_state(
                db=db,
                entity=product,
                entity_type="product",
                event="ready_for_publish",
                actor_id="system",
                meta={"source": "ai_job", "job_id": job_id},
            )
        except Exception:
            logger.exception(
                "Product state transition failed product_id=%s job_id=%s",
                getattr(product, "id", None),
                job_id,
            )

        db.commit()

    logger.info(
        "[ai] job done job_id=%s product_id=%s ms=%s",
        job_id,
        product_id,
        int((time.perf_counter() - t0) * 1000),
    )


def index_product(product_id: str) -> None:
    t0 = time.perf_counter()

    host, key, index_name = _meili_cfg()
    if not host or not key:
        logger.info("[meili] index skipped (not configured) product_id=%s", product_id)
        return

    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            logger.warning("[meili] product not found product_id=%s", product_id)
            return

        doc = {
            "id": p.id,
            "owner_id": p.owner_id,
            "status": p.status,
            "title": p.title,
            "description": p.description,
            "category_id": p.category_id,
            "tags": p.tags or [],
            "updated_at": p.updated_at.isoformat() if getattr(p, "updated_at", None) else None,
        }

    client = MeiliClient(host, key)
    idx = client.index(index_name)
    task = idx.add_documents([doc])

    if (uid := _task_uid(task)):
        _wait_task(client, uid)

    logger.info(
        "[meili] indexed product_id=%s index=%s ms=%s",
        product_id,
        index_name,
        int((time.perf_counter() - t0) * 1000),
    )