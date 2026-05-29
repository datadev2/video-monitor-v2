from datetime import timedelta

from celery import Celery

from src.config import config

celery_app = Celery(
    "video-probe-worker",
    broker=config.redis_dsn.unicode_string(),
    backend=config.redis_dsn.unicode_string(),
    include=[
        "src.video_probe.tasks",
    ],
)

celery_app.conf.update(
    timezone="Europe/Amsterdam",
    worker_pool_restarts=True,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


celery_app.conf.schedule = {
    "run_monitoring": {
        "task": "run_video_probes_task",
        "schedule": timedelta(minutes=config.monitoring_run_interval_minutes),
    }
}
