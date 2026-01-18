import os
import logging
from typing import Optional
from uuid import UUID

from redis import Redis
from rq import Queue

logger = logging.getLogger(__name__)


# ============================================================
# REDIS / QUEUE HELPERS
# ============================================================

def _redis_url() -> str:
    """
    Единственный источник правды для Redis URL.
    """
    url = (os.getenv("REDIS_URL") or "").strip()
    return url or "redis://redis:6379/0"


def _queue_name(default: str = "clothing") -> str:
    """
    Имя очереди RQ (единое для API и worker).
    """
    name = (os.getenv("RQ_QUEUE") or "").strip()
    return name or default


def get_redis() -> Redis:
    """
    Инициализация Redis connection.
    decode_responses=False — безопасно для RQ.
    """
    return Redis.from_url(_redis_url(), decode_responses=False)


def get_queue(name: Optional[str] = None) -> Queue:
    """
    Получить очередь RQ.
    """
    conn = get_redis()
    qname = (name or _queue_name()).strip()
    return Queue(qname, connection=conn)


# ============================================================
# ENQUEUE: AI JOB
# ============================================================

def enqueue_process_job(ai_job_id: str) -> str:
    """
    Кладём задачу обработки AIJob.

    Используется:
    - ai_jobs.id (string PK, НЕ UUID)
    """
    if not ai_job_id:
        raise ValueError("ai_job_id is required")

    q = get_queue()

    rq_job = q.enqueue(
        "jobs.process_ai_job",
        ai_job_id,
        job_timeout=int(os.getenv("RQ_JOB_TIMEOUT", "600")),     # 10 минут
        result_ttl=int(os.getenv("RQ_RESULT_TTL", "3600")),      # 1 час
        failure_ttl=int(os.getenv("RQ_FAILURE_TTL", "86400")),  # 24 часа
    )

    logger.info(
        "[rq] enqueue process_ai_job rq_id=%s ai_job_id=%s queue=%s redis=%s",
        rq_job.id,
        ai_job_id,
        q.name,
        _redis_url(),
    )

    return rq_job.id


# ============================================================
# ENQUEUE: PRODUCT INDEX (UUID ONLY)
# ============================================================

def enqueue_index_product(product_id_uuid: UUID) -> str:
    """
    Кладём задачу индексации товара в поиск (MeiliSearch).

    🔒 CONTRACT:
    - принимаем ТОЛЬКО products.id_uuid
    - legacy products.id запрещён
    """
    if not product_id_uuid:
        raise ValueError("product_id_uuid is required")

    product_uuid_str = str(product_id_uuid)

    q = get_queue()

    rq_job = q.enqueue(
        "jobs.index_product",
        product_uuid_str,
        job_timeout=int(os.getenv("RQ_INDEX_TIMEOUT", "120")),   # 2 минуты
        result_ttl=int(os.getenv("RQ_RESULT_TTL", "3600")),
        failure_ttl=int(os.getenv("RQ_FAILURE_TTL", "86400")),
    )

    logger.info(
        "[rq] enqueue index_product rq_id=%s product_id_uuid=%s queue=%s redis=%s",
        rq_job.id,
        product_uuid_str,
        q.name,
        _redis_url(),
    )

    return rq_job.id