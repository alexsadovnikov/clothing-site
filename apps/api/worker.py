import os
import logging

from redis import Redis
from rq import Worker, Queue, Connection

import jobs

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("worker")


# ============================================================
# REDIS / QUEUES
# ============================================================

def _redis_url() -> str:
    url = (os.getenv("REDIS_URL") or "").strip()
    return url or "redis://redis:6379/0"


def _queues() -> list[str]:
    raw = (os.getenv("RQ_QUEUES") or "").strip()
    if raw:
        return [q.strip() for q in raw.split(",") if q.strip()]

    q = (os.getenv("RQ_QUEUE") or "").strip()
    return [q or "clothing"]


# ============================================================
# ENTRYPOINT
# ============================================================

def main() -> None:
    redis_url = _redis_url()
    qnames = _queues()

    logger.info("[worker] starting")
    logger.info("[worker] redis=%s", redis_url)
    logger.info("[worker] queues=%s", qnames)

    # init Meili once on worker startup
    try:
        logger.info("[worker] init meili")
        jobs.init_meili()
        logger.info("[worker] meili ready")
    except Exception:
        logger.exception("[worker] meili init failed")

    conn = Redis.from_url(redis_url)
    queues = [Queue(name, connection=conn) for name in qnames]

    with Connection(conn):
        worker = Worker(queues)
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()