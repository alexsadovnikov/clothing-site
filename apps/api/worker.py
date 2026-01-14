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


def _redis_url() -> str:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        url = "redis://redis:6379/0"
    return url


def _queues() -> list[str]:
    """
    1) Если задано RQ_QUEUES="q1,q2" — слушаем список
    2) Иначе слушаем RQ_QUEUE
    """
    raw = (os.getenv("RQ_QUEUES") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]

    q = (os.getenv("RQ_QUEUE") or "").strip()
    return [q or "clothing"]


def main() -> None:
    redis_url = _redis_url()
    qnames = _queues()

    logger.info("[worker] starting...")
    logger.info("[worker] REDIS_URL=%s", redis_url)
    logger.info("[worker] queues=%s", qnames)

    # Meili init (один раз на старт воркера)
    try:
        logger.info("[worker] init meili...")
        jobs.init_meili()
        logger.info("[worker] meili init done")
    except Exception as e:
        logger.exception("[worker] meili init failed: %s", e)

    conn = Redis.from_url(redis_url)
    queues = [Queue(name, connection=conn) for name in qnames]

    with Connection(conn):
        w = Worker(queues)
        # with_scheduler=True чтобы работали scheduled jobs, если ты их используешь
        w.work(with_scheduler=True)


if __name__ == "__main__":
    main()