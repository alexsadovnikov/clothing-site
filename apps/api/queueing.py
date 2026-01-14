import os
import logging
from typing import Optional

from redis import Redis
from rq import Queue

logger = logging.getLogger(__name__)


def _redis_url() -> str:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        # fallback (на всякий)
        url = "redis://redis:6379/0"
    return url


def _queue_name(default: str = "clothing") -> str:
    # главный источник истины
    name = (os.getenv("RQ_QUEUE") or "").strip()
    return name or default


def get_redis() -> Redis:
    return Redis.from_url(_redis_url())


def get_queue(name: Optional[str] = None) -> Queue:
    conn = get_redis()
    qname = (name or _queue_name()).strip()
    return Queue(qname, connection=conn)


def enqueue_process_job(job_id: str) -> str:
    """
    Кладём задачу обработки AIJob.
    Возвращаем job.id в RQ.
    """
    q = get_queue()
    rq_job = q.enqueue(
        "jobs.process_ai_job",
        job_id,
        job_timeout=int(os.getenv("RQ_JOB_TIMEOUT", "600")),  # 10 минут по умолчанию
        result_ttl=int(os.getenv("RQ_RESULT_TTL", "3600")),   # 1 час
        failure_ttl=int(os.getenv("RQ_FAILURE_TTL", "86400")),# 24 часа
    )
    logger.info("enqueued process_ai_job: rq_id=%s job_id=%s queue=%s redis=%s",
                rq_job.id, job_id, q.name, _redis_url())
    return rq_job.id


def enqueue_index_product(product_id: str) -> str:
    """
    Кладём задачу индексации товара в Meili.
    """
    q = get_queue()
    rq_job = q.enqueue(
        "jobs.index_product",
        product_id,
        job_timeout=int(os.getenv("RQ_INDEX_TIMEOUT", "120")),  # 2 минуты
        result_ttl=int(os.getenv("RQ_RESULT_TTL", "3600")),
        failure_ttl=int(os.getenv("RQ_FAILURE_TTL", "86400")),
    )
    logger.info("enqueued index_product: rq_id=%s product_id=%s queue=%s redis=%s",
                rq_job.id, product_id, q.name, _redis_url())
    return rq_job.id