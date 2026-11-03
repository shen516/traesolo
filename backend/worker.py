"""RQ Worker 入口：python worker.py"""

import os

os.environ.setdefault("RUN_SCHEDULER", "0")

from redis import Redis
from rq import Worker, Queue

from services.redis_client import load_redis_config


def main():
    try:
        from services.training_service import training_service
        n = training_service.fail_abandoned_running_records(force=True)
        if n:
            print(f"Marked {n} stale training record(s) as failed")
    except Exception as e:
        print(f"stale training recovery failed: {e}")

    cfg = load_redis_config()
    url = cfg.get("url") or os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
    conn = Redis.from_url(url)

    try:
        from services.crawler_service import crawler_service
        from services.scheduled_tasks import register_all
        from services.scheduler_service import scheduler

        register_all(scheduler, crawler_service, enable_defaults=False)
        print(f"Registered {len(scheduler._registry)} scheduled tasks (scheduler not started)")
    except Exception as e:
        print(f"scheduled task registration failed: {e}")

    queues = [Queue("default", connection=conn), Queue("train", connection=conn), Queue("crawl", connection=conn)]
    worker = Worker(queues, connection=conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
