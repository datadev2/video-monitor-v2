from src.analytics.coros import calculate_analytics_and_push_to_redis
from src.celery_app import celery_app

from src.utils import event_loop
from src.video_probe.coros import run_video_probes


@celery_app.task(name="run_monitoring_and_calculate_analytics_task")
def run_monitoring_and_calculate_analytics_task():
    loop = event_loop()
    loop.run_until_complete(run_video_probes())
    loop.run_until_complete(calculate_analytics_and_push_to_redis())
