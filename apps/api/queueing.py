import os
from redis import Redis
from rq import Queue

def _queue() -> Queue:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is not set (remember: redis has password)")
    conn = Redis.from_url(redis_url)
    return Queue("clothing", connection=conn)

def enqueue_process_job(job_id: str):
    q = _queue()
    q.enqueue("jobs.process_ai_job", job_id)

def enqueue_index_product(product_id: str):
    q = _queue()
    q.enqueue("jobs.index_product", product_id)