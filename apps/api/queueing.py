# apps/api/queueing.py
from __future__ import annotations

import os
import logging
from typing import Optional, List

from redis import Redis
from rq import Queue

# Retry API differs across RQ versions; make it version-safe.
try:
    # RQ 1.x (including 1.16.2) exposes Retry at top-level.
    from rq import Retry  # type: ignore
except Exception:  # pragma: no cover
    Retry = None  # type: ignore

logger = logging.getLogger(__name__)

# ============================================================
# CONTRACT: canonical function paths (single source of truth)
# ============================================================

PROCESS_AI_JOB_FUNC = "apps.api.jobs.process_ai_job"
INDEX_PRODUCT_FUNC = "apps.api.jobs.index_product"


# ============================================================
# ENV helpers
# ============================================================

def _redis_url() -> str:
    url = (os.getenv("REDIS_URL") or "").strip()
    return url or "redis://redis:6379/0"


def _queue_name(default: str = "clothing") -> str:
    name = (os.getenv("RQ_QUEUE") or "").strip()
    return name or default


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _retry_intervals() -> List[int]:
    """
    Env example:
      RQ_RETRY_INTERVALS="10,30,60,180,300"
    """
    raw = (os.getenv("RQ_RETRY_INTERVALS") or "").strip()
    if not raw:
        return [10, 30, 60, 180, 300]

    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue

    return out or [10, 30, 60, 180, 300]


def _retry_max() -> int:
    """
    Env:
      RQ_RETRY_MAX="5"
    Default: len(intervals)
    """
    raw = (os.getenv("RQ_RETRY_MAX") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return len(_retry_intervals())


def _make_retry() -> Optional["Retry"]:
    """
    Create Retry object if supported by installed RQ.
    If Retry is unavailable, return None (no retries) but NEVER crash API.
    """
    if Retry is None:
        return None
    intervals = _retry_intervals()
    max_retries = _retry_max()
    return Retry(max=max_retries, interval=intervals)


# ============================================================
# Redis / Queue
# ============================================================

def get_redis() -> Redis:
    # decode_responses=False — safe for RQ (stores binary payloads)
    return Redis.from_url(_redis_url(), decode_responses=False)


def get_queue(name: Optional[str] = None) -> Queue:
    conn = get_redis()
    qname = (name or _queue_name()).strip()
    return Queue(qname, connection=conn)


# ============================================================
# Idempotent job_id helpers
# ============================================================

def _job_id_ai(ai_job_id: str) -> str:
    # Deterministic idempotent key for same ai_jobs.id
    return f"ai-{ai_job_id}"


def _job_id_index(product_id: str) -> str:
    return f"index-{product_id}"


def _log(event: str, request_id: Optional[str], **fields) -> None:
    """
    Structured log in key=value to be grep/Loki/ELK-friendly.
    """
    base = {"event": event, "request_id": request_id or "-"}
    base.update(fields)
    msg = " ".join([f"{k}={v}" for k, v in base.items()])
    logger.info(msg)


# ============================================================
# ENQUEUE: AI JOB
# ============================================================

def enqueue_process_job(ai_job_id: str, request_id: Optional[str] = None) -> str:
    """
    Enqueue processing of AIJob.

    CONTRACT:
      - ai_job_id: ai_jobs.id (string PK)
      - deterministic job_id -> idempotency
      - canonical function path -> stable import in worker
      - retry strategy at RQ level (if supported)
    """
    if not ai_job_id:
        raise ValueError("ai_job_id is required")

    q = get_queue()
    retry = _make_retry()

    rq_job = q.enqueue(
        PROCESS_AI_JOB_FUNC,
        ai_job_id,
        job_id=_job_id_ai(ai_job_id),
        retry=retry,  # None is allowed (no retry) and should not crash
        job_timeout=_int_env("RQ_JOB_TIMEOUT", 600),      # 10 minutes
        result_ttl=_int_env("RQ_RESULT_TTL", 3600),       # 1 hour
        failure_ttl=_int_env("RQ_FAILURE_TTL", 86400),    # 24 hours
        meta={"request_id": request_id or None},
    )

    _log(
        "rq_enqueue_ai",
        request_id,
        rq_id=rq_job.id,
        ai_job_id=ai_job_id,
        queue=q.name,
        func=PROCESS_AI_JOB_FUNC,
        redis=_redis_url(),
        retry_enabled=bool(retry),
        retry_max=_retry_max(),
        retry_intervals=",".join(map(str, _retry_intervals())),
    )

    return rq_job.id


# ============================================================
# ENQUEUE: PRODUCT INDEX
# ============================================================

def enqueue_index_product(product_id: str, request_id: Optional[str] = None) -> str:
    """
    Enqueue indexing product into MeiliSearch.

    CONTRACT:
      - product_id is Product.id (string PK)
      - deterministic job_id -> idempotency
      - canonical function path
    """
    if not product_id:
        raise ValueError("product_id is required")

    q = get_queue()
    retry = _make_retry()

    rq_job = q.enqueue(
        INDEX_PRODUCT_FUNC,
        product_id,
        job_id=_job_id_index(product_id),
        retry=retry,
        job_timeout=_int_env("RQ_INDEX_TIMEOUT", 120),    # 2 minutes
        result_ttl=_int_env("RQ_RESULT_TTL", 3600),
        failure_ttl=_int_env("RQ_FAILURE_TTL", 86400),
        meta={"request_id": request_id or None},
    )

    _log(
        "rq_enqueue_index",
        request_id,
        rq_id=rq_job.id,
        product_id=product_id,
        queue=q.name,
        func=INDEX_PRODUCT_FUNC,
        redis=_redis_url(),
        retry_enabled=bool(retry),
        retry_max=_retry_max(),
        retry_intervals=",".join(map(str, _retry_intervals())),
    )

    return rq_job.id