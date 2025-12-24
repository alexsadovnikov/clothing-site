import os
from redis import Redis
from rq import Worker, Queue, Connection

def main():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is not set")

    conn = Redis.from_url(redis_url)

    with Connection(conn):
        qs = [Queue("clothing")]
        w = Worker(qs)
        w.work()

if __name__ == "__main__":
    main()