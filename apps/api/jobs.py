from __future__ import annotations

import os
import time
import logging
from typing import Optional, Tuple

import requests
from meilisearch import Client as MeiliClient

from apps.api.db import SessionLocal
from apps.api.models import (
    AIJob,
    Media,
    Product,
    ProductState,
    AIJobState,
    AIJobStage,
)
from apps.api.state_service import change_state

logger = logging.getLogger(__name__)

_MEILI_FILTERABLE = ["status", "owner_id", "category_id", "tags"]
_MEILI_SORTABLE = ["updated_at"]


# ============================================================
# PROGRESS NORMALIZATION
# ============================================================

STAGE_PROGRESS: dict[AIJobStage, int] = {
    AIJobStage.QUEUED: 0,
    AIJobStage.ANALYZE_REQUEST: 10,
    AIJobStage.AI_PROCESSING: 30,
    AIJobStage.AI_RESPONSE_RECEIVED: 60,
    AIJobStage.PRODUCT_CREATE: 80,
    AIJobStage.STATE_TRANSITION: 90,
    AIJobStage.DONE: 100,
    AIJobStage.FAILED: 100,
}


def _apply_stage(job: AIJob, stage: AIJobStage, message: str | None = None) -> None:
    job.set_stage(stage, message)
    job.progress = STAGE_PROGRESS.get(stage, job.progress)

    if stage == AIJobStage.DONE:
        job.status = AIJobState.SUCCEEDED.value
    elif stage == AIJobStage.FAILED:
        job.status = AIJobState.FAILED.value
    else:
        job.status = AIJobState.RUNNING.value


# ============================================================
# MEILI
# ============================================================

def _meili_cfg() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    host = (os.getenv("MEILI_HOST") or "").strip()
    key = (os.getenv("MEILI_MASTER_KEY") or "").strip()
    index_name = (os.getenv("MEILI_INDEX") or "products").strip()

    if not host or not key:
        return None, None, None

    if not host.startswith("http"):
        host = f"http://{host}"

    return host, key, index_name


def init_meili() -> None:
    host, key, index_name = _meili_cfg()
    if not host or not key:
        logger.info("[meili] init skipped")
        return

    client = MeiliClient(host, key)

    try:
        idx = client.get_index(index_name)
    except Exception:
        client.create_index(index_name, {"primaryKey": "id"})
        idx = client.get_index(index_name)

    idx.update_filterable_attributes(_MEILI_FILTERABLE)
    idx.update_sortable_attributes(_MEILI_SORTABLE)


# ============================================================
# HELPERS
# ============================================================

def _update_product_text(product: Product, ai: dict) -> None:
    if not product.title and ai.get("title_suggested"):
        product.title = ai["title_suggested"]

    if not product.description:
        product.description = ai.get("description_draft") or "Описание будет уточнено."


def _fail_job(
    *,
    db,
    job: AIJob,
    stage: AIJobStage,
    code: str,
    message: str,
    raw_error: str | None = None,
) -> None:
    _apply_stage(job, stage, message)
    _apply_stage(job, AIJobStage.FAILED, "Ошибка выполнения")

    job.error_stage = stage.value
    job.error_code = code
    job.error_message = message
    job.error = raw_error or message

    db.commit()


def _ai_internal_base_url() -> str:
    return (os.getenv("AI_INTERNAL_URL") or "http://api:8001").strip().rstrip("/")


def _ai_internal_token() -> str:
    return (os.getenv("AI_INTERNAL_TOKEN") or "").strip()


def _safe_json(resp: requests.Response) -> dict:
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("AI response must be JSON object")
    return data


# ============================================================
# MAIN WORKER
# ============================================================

def process_ai_job(job_id: str) -> None:
    t0 = time.perf_counter()

    # ===== LOAD JOB =====
    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not job:
            logger.warning("ai_job not found job_id=%s", job_id)
            return

        if job.status == AIJobState.SUCCEEDED.value and job.draft_product_id:
            logger.info("job already completed %s", job_id)
            return

        _apply_stage(job, AIJobStage.ANALYZE_REQUEST, "Подготовка запроса к AI")
        db.commit()

        media = db.query(Media).filter(Media.id == job.media_id).first()
        if not media:
            _fail_job(
                db=db,
                job=job,
                stage=AIJobStage.ANALYZE_REQUEST,
                code="MEDIA_NOT_FOUND",
                message="Файл изображения не найден",
            )
            return

        bucket = media.bucket
        object_key = media.object_key

    # ===== CALL AI =====
    try:
        with SessionLocal() as db:
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            _apply_stage(job, AIJobStage.AI_PROCESSING, "AI обрабатывает изображение")
            db.commit()

        headers = {"Content-Type": "application/json"}
        token = _ai_internal_token()
        if token:
            headers["X-AI-Internal-Token"] = token

        resp = requests.post(
            f"{_ai_internal_base_url()}/v1/analyze",
            json={"bucket": bucket, "object_key": object_key},
            headers=headers,
            timeout=(5, 180),
        )

        if resp.status_code >= 400:
            raise RuntimeError(resp.text)

        result = _safe_json(resp)

        logger.warning("AI RESULT FULL: %s", result)
        logger.warning("AI RESULT KEYS: %s", list(result.keys()))
        logger.warning("AI TITLE RAW: %s", result.get("title_suggested"))


        with SessionLocal() as db:
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            _apply_stage(job, AIJobStage.AI_RESPONSE_RECEIVED, "Ответ AI получен")
            db.commit()

    except Exception as e:
        with SessionLocal() as db:
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            if job:
                _fail_job(
                    db=db,
                    job=job,
                    stage=AIJobStage.AI_PROCESSING,
                    code="AI_REQUEST_FAILED",
                    message="Ошибка при обращении к AI",
                    raw_error=str(e),
                )
        logger.exception("AI processing failed job_id=%s", job_id)
        return

    # ===== CREATE PRODUCT =====
    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        _apply_stage(job, AIJobStage.PRODUCT_CREATE, "Создание карточки товара")

        product = Product(
            owner_id=job.owner_id,
            status=ProductState.DRAFT_EMPTY.value,
            title=None,
            attributes=result.get("attributes") or {},
            tags=result.get("tags") or [],
        )

        _update_product_text(product, result)

        if not product.title:
            product.title = "Товар (черновик)"

        db.add(product)
        db.flush()

        job.draft_product_id = product.id
        job.result_json = result

        try:
            _apply_stage(job, AIJobStage.STATE_TRANSITION, "Применение бизнес-статуса")

            change_state(
                db=db,
                entity=product,
                entity_type="product",
                event="ready_for_publish",
                actor_id="system",
                meta={"source": "ai_job", "job_id": job_id},
            )

            _apply_stage(job, AIJobStage.DONE, "Готово")

            logger.warning(
                "STAGE DEBUG: stage=%s progress=%s status=%s",
                job.stage,
                job.progress,
                job.status,
            )

        except Exception as e:
            _fail_job(
                db=db,
                job=job,
                stage=AIJobStage.STATE_TRANSITION,
                code="STATE_TRANSITION_FAILED",
                message="Ошибка перехода состояния продукта",
                raw_error=str(e),
            )
            logger.exception("State transition failed job_id=%s", job_id)
            return

        db.commit()
        product_id = job.draft_product_id

    logger.info(
        "[ai] job done job_id=%s product_id=%s ms=%s",
        job_id,
        product_id,
        int((time.perf_counter() - t0) * 1000),
    )