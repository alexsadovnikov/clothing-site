import os
import logging

from redis import Redis
from rq import Worker, Queue, Connection

from sqlalchemy.orm import Session

import jobs
from db import SessionLocal
from models import Product, AIJob
from state_service import change_state

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("worker")


def _redis_url() -> str:
    url = (os.getenv("REDIS_URL") or "").strip()
    return url or "redis://redis:6379/0"


def _queues() -> list[str]:
    raw = (os.getenv("RQ_QUEUES") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]

    q = (os.getenv("RQ_QUEUE") or "").strip()
    return [q or "clothing"]


# ============================================================
# ОБЁРТКА ДЛЯ JOB ВЫПОЛНЕНИЯ С STATE-MACHINE
# ============================================================

def process_job_with_state(job_id: str) -> None:
    """
    Обёртка над jobs.process_job(job_id),
    которая гарантирует корректные переходы состояний.
    """
    db: Session = SessionLocal()

    try:
        ai_job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not ai_job:
            logger.error("[worker] AIJob not found: %s", job_id)
            return

        product = db.query(Product).filter(Product.id == ai_job.product_id).first()
        if not product:
            logger.error("[worker] Product not found for job: %s", job_id)
            return

        # ====================================================
        # STATE: MEDIA_READY → AI_PROCESSING
        # ====================================================
        change_state(
            session=db,
            entity=product,
            entity_type="product",
            event="ai_processing",
            actor="worker",
        )

        ai_job.state = "processing"
        db.commit()

        # ====================================================
        # ВЫЗОВ РЕАЛЬНОЙ AI-ЛОГИКИ
        # ====================================================
        jobs.process_job(job_id)

        # ====================================================
        # STATE: AI_PROCESSING → AI_READY
        # ====================================================
        change_state(
            session=db,
            entity=product,
            entity_type="product",
            event="ai_done",
            actor="worker",
        )

        ai_job.state = "done"
        db.commit()

        logger.info("[worker] job done: %s", job_id)

    except Exception as e:
        logger.exception("[worker] job failed: %s", job_id)

        try:
            # ====================================================
            # STATE: AI_PROCESSING → AI_FAILED
            # ====================================================
            change_state(
                session=db,
                entity=product,
                entity_type="product",
                event="ai_failed",
                actor="worker",
            )
            ai_job.state = "failed"
            ai_job.error = str(e)
            db.commit()
        except Exception:
            logger.exception("[worker] failed to update error state")

    finally:
        db.close()


# ============================================================
# ENTRYPOINT
# ============================================================

def main() -> None:
    redis_url = _redis_url()
    qnames = _queues()

    logger.info("[worker] starting...")
    logger.info("[worker] REDIS_URL=%s", redis_url)
    logger.info("[worker] queues=%s", qnames)

    # Meili init
    try:
        logger.info("[worker] init meili...")
        jobs.init_meili()
        logger.info("[worker] meili init done")
    except Exception as e:
        logger.exception("[worker] meili init failed: %s", e)

    conn = Redis.from_url(redis_url)
    queues = [Queue(name, connection=conn) for name in qnames]

    with Connection(conn):
        worker = Worker(
            queues,
            # 👇 КЛЮЧЕВОЕ ИЗМЕНЕНИЕ
            job_class=None,
            exception_handlers=None,
        )
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()